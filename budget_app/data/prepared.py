"""Prepared immutable budget bundles and versioned, atomic persistence.

The builder performs the expensive classification and grouping work once per
source version.  Sessions consume compact copies through the helpers on
``PreparedBudgetBundle`` and never receive a mutable process-wide frame.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import tempfile
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .domain import add_scope_column, build_snapshot, overview_totals, robust_change_signals
from .models import (
    FUND_SCOPE_LABELS,
    NORMALIZED_COLUMNS,
    BudgetSnapshot,
    PreparedBudgetBundle,
    SnapshotMetadata,
)
from .normalize import DataValidationError, normalize_frame

LOG = logging.getLogger(__name__)
PREPARATION_SCHEMA_VERSION = 1
PREPARED_COLUMNS = (*NORMALIZED_COLUMNS, "fund_scope")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def content_hash(rows: pd.DataFrame) -> str:
    """Return a deterministic SHA-256 hash of canonical row values and order."""

    canonical = rows.loc[:, [column for column in PREPARED_COLUMNS if column in rows.columns]].copy()
    # Hashing a CSV representation keeps the digest stable across pyarrow
    # versions while retaining source order, including duplicate object IDs.
    payload = canonical.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_manifest(directory: Path, paths: list[Path]) -> dict[str, dict[str, int | str]]:
    manifest: dict[str, dict[str, int | str]] = {}
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest[str(path.relative_to(directory))] = {"sha256": digest, "size": path.stat().st_size}
    return manifest


def _freeze_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Mark backing arrays read-only as a best-effort contract guard."""

    result = frame.reset_index(drop=True)
    for column in result.columns:
        with suppress(ValueError, AttributeError):
            result[column].to_numpy(copy=False).setflags(write=False)
    return result


def _choices(rows: pd.DataFrame) -> dict[str, Any]:
    choices: dict[str, Any] = {
        "years": tuple(str(int(value)) for value in sorted(rows["fiscal_year"].unique())),
        "flows": tuple(str(value) for value in rows["expense_revenue"].drop_duplicates()),
        "fund_scopes": tuple(FUND_SCOPE_LABELS),
    }
    for dimension in ("department", "fund", "category", "fund_category", "fund_scope"):
        choices[dimension] = tuple(
            str(value) for value in sorted(rows[dimension].fillna("").replace("", "Unspecified").unique())
        )
    for department, group in rows.groupby("department", sort=True, dropna=False):
        department_name = str(department or "Unspecified")
        choices[f"funds_by_department:{department_name}"] = tuple(
            str(value) for value in sorted(group["fund"].fillna("").replace("", "Unspecified").unique())
        )
        for fund, fund_group in group.groupby("fund", sort=True, dropna=False):
            fund_name = str(fund or "Unspecified")
            choices[f"categories_by_department_fund:{department_name}\x1f{fund_name}"] = tuple(
                str(value)
                for value in sorted(fund_group["category"].fillna("").replace("", "Unspecified").unique())
            )
    return choices


def _aggregates(rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build compact tables used by Overview, Explorer, What Changed, and Lab."""

    tables: dict[str, pd.DataFrame] = {"overview_totals": overview_totals(rows)}
    scopes = rows[["fiscal_year", "expense_revenue", "fund_scope", "fund", "amount", "object_id"]].copy()
    all_scopes = scopes.copy()
    all_scopes["fund_scope"] = "all_funds"
    scoped = pd.concat([scopes, all_scopes], ignore_index=True)
    grouped = (
        scoped.groupby(["fiscal_year", "expense_revenue", "fund_scope"], as_index=False)
        .agg(amount=("amount", "sum"), line_items=("object_id", "size"))
        .sort_values(["fiscal_year", "expense_revenue", "fund_scope"])
    )
    tables["totals_by_year_flow_scope"] = grouped.reset_index(drop=True)
    parent_columns = {"department": (), "fund": ("department",), "category": ("department", "fund")}
    for dimension in ("department", "fund", "category"):
        context_columns = [*parent_columns[dimension], dimension]
        hierarchy = rows[
            ["fiscal_year", "expense_revenue", "fund_scope", *context_columns, "amount", "object_id"]
        ].copy()
        hierarchy["name"] = hierarchy[dimension].fillna("").replace("", "Unspecified")
        hierarchy = hierarchy.drop(columns=[dimension])
        for parent in parent_columns[dimension]:
            hierarchy[parent] = hierarchy[parent].fillna("").replace("", "Unspecified")
        all_hierarchy = hierarchy.copy()
        all_hierarchy["fund_scope"] = "all_funds"
        hierarchy = pd.concat([hierarchy, all_hierarchy], ignore_index=True)
        hierarchy = (
            hierarchy.groupby(
                ["fiscal_year", "expense_revenue", "fund_scope", *parent_columns[dimension], "name"],
                as_index=False,
            )
            .agg(amount=("amount", "sum"), line_items=("object_id", "size"))
            .sort_values(
                ["fiscal_year", "expense_revenue", "fund_scope", "amount", "name"],
                ascending=[True, True, True, False, True],
            )
        )
        hierarchy["share"] = hierarchy["amount"] / hierarchy.groupby(
            ["fiscal_year", "expense_revenue", "fund_scope", *parent_columns[dimension]]
        )["amount"].transform("sum")
        hierarchy["share"] = hierarchy["share"].fillna(0.0)
        tables[f"hierarchy_{dimension}"] = hierarchy.reset_index(drop=True)
    history_parts: list[pd.DataFrame] = []
    for dimension in ("department", "fund", "category"):
        history = rows[["fiscal_year", "expense_revenue", "fund_scope", dimension, "amount"]].copy()
        history["entity"] = history[dimension].fillna("").replace("", "Unspecified")
        history = history.drop(columns=[dimension])
        all_history = history.copy()
        all_history["fund_scope"] = "all_funds"
        history_parts.append(pd.concat([history, all_history], ignore_index=True).assign(dimension=dimension))
    history = pd.concat(history_parts, ignore_index=True)
    tables["history"] = (
        history.groupby(
            ["dimension", "entity", "fiscal_year", "expense_revenue", "fund_scope"], as_index=False
        )
        .agg(amount=("amount", "sum"))
        .sort_values(["dimension", "entity", "fiscal_year", "expense_revenue", "fund_scope"])
        .reset_index(drop=True)
    )
    tables["fund_scope_totals"] = (
        scoped.assign(
            expenses=scoped["amount"].where(scoped["expense_revenue"].eq("Expenses"), 0.0),
            revenues=scoped["amount"].where(scoped["expense_revenue"].eq("Revenues"), 0.0),
        )
        .groupby(["fiscal_year", "fund_scope"], as_index=False)
        .agg(
            expenses=("expenses", "sum"),
            revenues=("revenues", "sum"),
            line_items=("object_id", "size"),
            funds=("fund", "nunique"),
        )
        .assign(fund_scope_label=lambda value: value["fund_scope"].map(FUND_SCOPE_LABELS))
    )
    tables["signals_department"] = robust_change_signals(rows)
    tables["record_counts"] = (
        rows.assign(
            department=rows["department"].fillna("").replace("", "Unspecified"),
            fund=rows["fund"].fillna("").replace("", "Unspecified"),
            category=rows["category"].fillna("").replace("", "Unspecified"),
        )
        .groupby(
            ["fiscal_year", "expense_revenue", "fund_scope", "department", "fund", "category"],
            as_index=False,
        )
        .agg(line_items=("object_id", "size"))
    )
    return {name: _freeze_frame(frame) for name, frame in tables.items()}


def _indexes(rows: pd.DataFrame) -> dict[str, dict[Any, tuple[int, ...]]]:
    indexes: dict[str, dict[Any, tuple[int, ...]]] = {}
    for column in ("object_id", "department", "fund", "category", "fund_scope"):
        mapping: dict[Any, list[int]] = {}
        for position, value in enumerate(rows[column].tolist()):
            key = value.item() if hasattr(value, "item") else value
            mapping.setdefault(key, []).append(position)
        indexes[column] = {key: tuple(positions) for key, positions in mapping.items()}
    return indexes


def _validation(rows: pd.DataFrame, metadata: SnapshotMetadata) -> dict[str, Any]:
    expected_hash = metadata.content_hash or content_hash(rows)
    known = rows.loc[rows["fund_scope"].ne("unknown")]
    expense_total = float(rows.loc[rows["expense_revenue"].eq("Expenses"), "amount"].sum())
    revenue_total = float(rows.loc[rows["expense_revenue"].eq("Revenues"), "amount"].sum())
    known_expense_total = float(known.loc[known["expense_revenue"].eq("Expenses"), "amount"].sum())
    known_revenue_total = float(known.loc[known["expense_revenue"].eq("Revenues"), "amount"].sum())
    return {
        "schema": tuple(rows.columns) == PREPARED_COLUMNS,
        "row_count": len(rows) == metadata.row_count,
        "content_hash": content_hash(rows) == expected_hash,
        "years": tuple(sorted(int(v) for v in rows["fiscal_year"].unique())) == metadata.years,
        "reconciliation": math.isclose(expense_total, metadata.all_funds_expenses, rel_tol=1e-9, abs_tol=1e-6)
        and math.isclose(revenue_total, metadata.all_funds_revenues, rel_tol=1e-9, abs_tol=1e-6)
        and math.isclose(known_expense_total, metadata.known_scope_expenses, rel_tol=1e-9, abs_tol=1e-6)
        and math.isclose(known_revenue_total, metadata.known_scope_revenues, rel_tol=1e-9, abs_tol=1e-6),
    }


def prepare_bundle(
    rows: pd.DataFrame,
    *,
    source_url: str,
    source_last_edit_date: int | None = None,
    generated_at: str | None = None,
    fetched_at: str | None = None,
    checked_at: str | None = None,
    prepared_at: str | None = None,
    version: str | None = None,
    schema_version: int = PREPARATION_SCHEMA_VERSION,
) -> PreparedBudgetBundle:
    """Normalize, classify, validate, and precompute one immutable bundle."""

    started = time.perf_counter()
    canonical = add_scope_column(rows)
    canonical = canonical.loc[:, [*NORMALIZED_COLUMNS, "fund_scope"]].reset_index(drop=True)
    digest = content_hash(canonical)
    bundle_version = version or f"v{schema_version}-{digest[:16]}"
    prepared_timestamp = prepared_at or _utc_now()
    checked_timestamp = checked_at or _utc_now()
    snapshot = build_snapshot(
        canonical,
        source_url=source_url,
        source_last_edit_date=source_last_edit_date,
        generated_at=generated_at,
        fetched_at=fetched_at,
        checked_at=checked_timestamp,
        prepared_at=prepared_timestamp,
        schema_version=schema_version,
        content_hash=digest,
        version=bundle_version,
    )
    metadata = snapshot.metadata
    validation = _validation(canonical, metadata)
    if not all(validation.values()):
        raise DataValidationError(f"Prepared bundle validation failed: {validation}")
    metadata = SnapshotMetadata.from_dict({**metadata.as_dict(), "validation_results": validation})
    snapshot = BudgetSnapshot(
        rows=_freeze_frame(canonical),
        generated_at=snapshot.generated_at,
        latest_year=snapshot.latest_year,
        years=snapshot.years,
        metadata=metadata,
        status=snapshot.status,
        status_message=snapshot.status_message,
        overview=_freeze_frame(snapshot.overview) if snapshot.overview is not None else None,
    )
    frozen_rows = snapshot.rows
    aggregates = _aggregates(frozen_rows)
    choices = _choices(frozen_rows)
    bundle = PreparedBudgetBundle(
        rows=frozen_rows,
        snapshot=snapshot,
        choices=choices,
        aggregates=aggregates,
        indexes=_indexes(frozen_rows),
        record_counts=aggregates["record_counts"],
    )
    LOG.info(
        "prepared budget bundle",
        extra={
            "stage": "prepare",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "row_count": len(frozen_rows),
            "version": bundle.version,
        },
    )
    return bundle


# Explicit alias for callers that prefer a class-like builder name.
build_prepared_bundle = prepare_bundle


class PreparedBundleStore:
    """Versioned bundle storage with atomic current-pointer promotion.

    A single process can safely read while another thread stages a bundle.  A
    pointer replacement is the only operation that changes what new readers
    observe, and the previous version remains available for rollback.
    """

    def __init__(self, cache_dir: Path | str, *, schema_version: int = PREPARATION_SCHEMA_VERSION):
        self.cache_dir = Path(cache_dir)
        self.schema_version = schema_version
        self.snapshots_dir = self.cache_dir / "snapshots"
        self.current_path = self.cache_dir / "current.json"
        self.legacy_rows_path = self.cache_dir / "approved-budgets.parquet"
        self.legacy_metadata_path = self.cache_dir / "approved-budgets.metadata.json"

    @staticmethod
    def _metadata_path(directory: Path) -> Path:
        return directory / "bundle.metadata.json"

    def _write_bundle_files(self, directory: Path, bundle: PreparedBudgetBundle) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        bundle.rows.to_parquet(directory / "rows.parquet", index=False)
        aggregate_dir = directory / "aggregates"
        aggregate_dir.mkdir(exist_ok=True)
        aggregate_manifest: dict[str, str] = {}
        for index, (name, table) in enumerate(bundle.aggregates.items()):
            filename = f"{index:04d}.parquet"
            table.to_parquet(aggregate_dir / filename, index=False)
            aggregate_manifest[name] = filename
        choices_path = directory / "choices.json"
        choices_path.write_text(
            json.dumps({key: list(values) for key, values in bundle.choices.items()}, ensure_ascii=False),
            encoding="utf-8",
        )
        artifact_paths = [directory / "rows.parquet", choices_path]
        artifact_paths.extend(aggregate_dir / filename for filename in aggregate_manifest.values())
        payload = {
            **bundle.metadata.as_dict(),
            "aggregate_manifest": aggregate_manifest,
            "prepared_columns": list(PREPARED_COLUMNS),
            "artifact_manifest": _file_manifest(directory, artifact_paths),
        }
        temporary = self._metadata_path(directory).with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self._metadata_path(directory))

    def _validate_directory(self, directory: Path) -> PreparedBudgetBundle:
        metadata_path = self._metadata_path(directory)
        metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_payload.get("prepared_columns") != list(PREPARED_COLUMNS):
            raise DataValidationError("Prepared bundle schema columns do not match")
        metadata = SnapshotMetadata.from_dict(metadata_payload)
        if metadata.schema_version != self.schema_version:
            raise DataValidationError("Unsupported prepared bundle schema version")
        rows = pd.read_parquet(directory / "rows.parquet")
        if tuple(rows.columns) != PREPARED_COLUMNS:
            raise DataValidationError("Prepared bundle rows schema does not match")
        if len(rows) != metadata.row_count or content_hash(rows) != metadata.content_hash:
            raise DataValidationError("Prepared bundle row count or content hash mismatch")
        artifact_manifest = metadata_payload.get("artifact_manifest", {})
        if not isinstance(artifact_manifest, dict) or not artifact_manifest:
            raise DataValidationError("Prepared bundle artifact manifest is missing")
        for relative, facts in artifact_manifest.items():
            path = directory / relative
            if not path.exists() or not isinstance(facts, dict):
                raise DataValidationError(f"Prepared bundle artifact is missing: {relative}")
            if path.stat().st_size != int(facts.get("size", -1)):
                raise DataValidationError(f"Prepared bundle artifact size mismatch: {relative}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != facts.get("sha256"):
                raise DataValidationError(f"Prepared bundle artifact hash mismatch: {relative}")
        checks = _validation(rows, metadata)
        if not all(checks.values()):
            raise DataValidationError(f"Prepared bundle validation failed on reopen: {checks}")
        snapshot = build_snapshot(
            rows,
            source_url=metadata.source_url,
            source_last_edit_date=metadata.source_last_edit_date,
            generated_at=metadata.generated_at,
            fetched_at=metadata.fetched_at,
            checked_at=metadata.checked_at,
            prepared_at=metadata.prepared_at,
            schema_version=metadata.schema_version,
            content_hash=metadata.content_hash,
            version=metadata.version,
            validation_results=metadata.validation_results,
        )
        snapshot = BudgetSnapshot(
            rows=_freeze_frame(rows),
            generated_at=snapshot.generated_at,
            latest_year=snapshot.latest_year,
            years=snapshot.years,
            metadata=metadata,
            status=snapshot.status,
            status_message=snapshot.status_message,
            overview=_freeze_frame(snapshot.overview) if snapshot.overview is not None else None,
        )
        choices_payload = json.loads((directory / "choices.json").read_text(encoding="utf-8"))
        choices = {key: tuple(str(value) for value in values) for key, values in choices_payload.items()}
        aggregate_manifest = metadata_payload.get("aggregate_manifest", {})
        required_aggregates = {
            "overview_totals",
            "totals_by_year_flow_scope",
            "hierarchy_department",
            "hierarchy_fund",
            "hierarchy_category",
            "history",
            "fund_scope_totals",
            "signals_department",
            "record_counts",
        }
        if not required_aggregates.issubset(aggregate_manifest):
            raise DataValidationError("Prepared bundle aggregate manifest is incomplete")
        aggregates = {
            name: _freeze_frame(pd.read_parquet(directory / "aggregates" / filename))
            for name, filename in aggregate_manifest.items()
        }
        return PreparedBudgetBundle(
            rows=snapshot.rows,
            snapshot=snapshot,
            choices=choices,
            aggregates=aggregates,
            indexes=_indexes(snapshot.rows),
            record_counts=aggregates.get("record_counts"),
        )

    def promote(self, bundle: PreparedBudgetBundle) -> PreparedBudgetBundle:
        """Stage, reopen, validate, then atomically promote ``bundle``."""

        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.snapshots_dir))
        final = self.snapshots_dir / bundle.version
        try:
            self._write_bundle_files(stage, bundle)
            verified = self._validate_directory(stage)
            if final.exists():
                # Reuse an already verified identical version.  A corrupt
                # directory is replaced from the fully validated stage.
                try:
                    self._validate_directory(final)
                except Exception:  # noqa: BLE001
                    shutil.rmtree(final)
                    os.replace(stage, final)
                else:
                    with suppress(FileNotFoundError):
                        shutil.rmtree(stage)
            else:
                os.replace(stage, final)
            pointer_tmp = self.current_path.with_suffix(".json.tmp")
            pointer_tmp.write_text(
                json.dumps({"version": verified.version}, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(pointer_tmp, self.current_path)
            return self._validate_directory(final)
        except Exception:
            with suppress(OSError):
                shutil.rmtree(stage)
            raise

    def load_version(self, version: str) -> PreparedBudgetBundle | None:
        try:
            return self._validate_directory(self.snapshots_dir / version)
        except (OSError, ValueError, TypeError, KeyError, DataValidationError):
            LOG.warning("invalid prepared budget version", extra={"version": version})
            return None

    def load_current(self) -> PreparedBudgetBundle | None:
        """Load current, then newest previous valid version, then migrate legacy."""

        candidates: list[str] = []
        if self.current_path.exists():
            with suppress(OSError, ValueError, TypeError, KeyError):
                pointer = json.loads(self.current_path.read_text(encoding="utf-8"))
                if pointer.get("version"):
                    candidates.append(str(pointer["version"]))
        if self.snapshots_dir.exists():
            candidates.extend(
                path.name
                for path in sorted(
                    self.snapshots_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
                )
                if path.is_dir() and not path.name.startswith(".staging-")
            )
        seen: set[str] = set()
        for version in candidates:
            if version in seen:
                continue
            seen.add(version)
            bundle = self.load_version(version)
            if bundle is not None:
                return bundle
        return self.migrate_legacy()

    def migrate_legacy(self) -> PreparedBudgetBundle | None:
        """Build a versioned bundle from the approved legacy pair without deleting it."""

        if not self.legacy_rows_path.exists() or not self.legacy_metadata_path.exists():
            return None
        try:
            payload = json.loads(self.legacy_metadata_path.read_text(encoding="utf-8"))
            metadata = SnapshotMetadata.from_dict(payload)
            rows = normalize_frame(pd.read_parquet(self.legacy_rows_path))
            bundle = prepare_bundle(
                rows,
                source_url=metadata.source_url,
                source_last_edit_date=metadata.source_last_edit_date,
                fetched_at=metadata.fetched_at,
                checked_at=metadata.checked_at,
                prepared_at=metadata.prepared_at,
                schema_version=self.schema_version,
            )
            return self.promote(bundle)
        except (OSError, ValueError, TypeError, KeyError, DataValidationError) as exc:
            LOG.warning("legacy budget cache migration failed: %s", exc)
            return None


# Backwards-friendly names for integration code and tests.
PreparedBudgetBundleStore = PreparedBundleStore
PreparedBundleBuilder = type(
    "PreparedBundleBuilder",
    (),
    {"build": staticmethod(prepare_bundle), "prepare": staticmethod(prepare_bundle)},
)
