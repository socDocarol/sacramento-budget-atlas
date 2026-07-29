"""Typed contracts for the Sacramento Approved Budgets data layer.

The UI should consume these small, pandas-backed objects rather than know about
ArcGIS response shapes.  The dataframe stored in :class:`BudgetSnapshot` is a
normalized eight-column contract and is safe to share between Shiny sessions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

Flow = Literal["Expenses", "Revenues"]
Scope = Literal[
    "all_funds",
    "general_fund",
    "measure_u",
    "enterprise_funds",
    "internal_service_funds",
    "other_governmental_or_restricted",
    "unknown",
]
SnapshotStatus = Literal["fresh", "stale", "error"]
CacheSource = Literal["memory", "disk-fresh", "disk-revalidated", "source", "stale-disk"]

NORMALIZED_COLUMNS: tuple[str, ...] = (
    "fiscal_year",
    "department",
    "fund",
    "category",
    "amount",
    "expense_revenue",
    "fund_category",
    "object_id",
)

FUND_SCOPE_LABELS: dict[str, str] = {
    "all_funds": "All funds total",
    "general_fund": "General Fund",
    "measure_u": "Measure U Fund",
    "enterprise_funds": "Enterprise Funds",
    "internal_service_funds": "Internal Service Funds",
    "other_governmental_or_restricted": "Other governmental / restricted funds",
    "unknown": "Unknown scope",
}


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """Validation and source facts written next to a cached parquet snapshot."""

    source_url: str
    source_last_edit_date: int | None
    generated_at: str
    fetched_at: str
    row_count: int
    years: tuple[int, ...]
    duplicate_object_ids: int = 0
    blank_departments: int = 0
    blank_funds: int = 0
    blank_categories: int = 0
    unknown_scopes: int = 0
    all_funds_expenses: float = 0.0
    all_funds_revenues: float = 0.0
    known_scope_expenses: float = 0.0
    known_scope_revenues: float = 0.0
    # ``fetched_at`` is the source timestamp of the last complete successful
    # promotion.  The following fields describe the prepared immutable bundle
    # and are intentionally optional for backwards-compatible legacy caches.
    checked_at: str | None = None
    prepared_at: str | None = None
    schema_version: int = 1
    content_hash: str = ""
    version: str = ""
    validation_results: Mapping[str, Any] = field(default_factory=dict, compare=False)
    artifact_manifest: Mapping[str, Any] = field(default_factory=dict, compare=False)

    @property
    def expense_reconciliation_delta(self) -> float:
        return self.all_funds_expenses - self.known_scope_expenses

    @property
    def revenue_reconciliation_delta(self) -> float:
        return self.all_funds_revenues - self.known_scope_revenues

    def as_dict(self) -> dict[str, object]:
        return {
            "source_url": self.source_url,
            "source_last_edit_date": self.source_last_edit_date,
            "generated_at": self.generated_at,
            "fetched_at": self.fetched_at,
            "row_count": self.row_count,
            "years": list(self.years),
            "duplicate_object_ids": self.duplicate_object_ids,
            "blank_departments": self.blank_departments,
            "blank_funds": self.blank_funds,
            "blank_categories": self.blank_categories,
            "unknown_scopes": self.unknown_scopes,
            "all_funds_expenses": self.all_funds_expenses,
            "all_funds_revenues": self.all_funds_revenues,
            "known_scope_expenses": self.known_scope_expenses,
            "known_scope_revenues": self.known_scope_revenues,
            "checked_at": self.checked_at,
            "prepared_at": self.prepared_at,
            "schema_version": self.schema_version,
            "content_hash": self.content_hash,
            "version": self.version,
            "validation_results": dict(self.validation_results),
            "artifact_manifest": dict(self.artifact_manifest),
        }

    @classmethod
    def from_dict(cls, values: dict[str, object]) -> SnapshotMetadata:
        years = tuple(int(value) for value in values.get("years", []))
        source_edit = values.get("source_last_edit_date")
        return cls(
            source_url=str(values.get("source_url", "")),
            source_last_edit_date=int(source_edit) if source_edit is not None else None,
            generated_at=str(values.get("generated_at", "")),
            fetched_at=str(values.get("fetched_at", "")),
            row_count=int(values.get("row_count", 0)),
            years=years,
            duplicate_object_ids=int(values.get("duplicate_object_ids", 0)),
            blank_departments=int(values.get("blank_departments", 0)),
            blank_funds=int(values.get("blank_funds", 0)),
            blank_categories=int(values.get("blank_categories", 0)),
            unknown_scopes=int(values.get("unknown_scopes", 0)),
            all_funds_expenses=float(values.get("all_funds_expenses", 0.0)),
            all_funds_revenues=float(values.get("all_funds_revenues", 0.0)),
            known_scope_expenses=float(values.get("known_scope_expenses", 0.0)),
            known_scope_revenues=float(values.get("known_scope_revenues", 0.0)),
            checked_at=(str(values["checked_at"]) if values.get("checked_at") is not None else None),
            prepared_at=(str(values["prepared_at"]) if values.get("prepared_at") is not None else None),
            schema_version=int(values.get("schema_version", 1)),
            content_hash=str(values.get("content_hash", "")),
            version=str(values.get("version", "")),
            validation_results=(
                dict(values.get("validation_results", {}))
                if isinstance(values.get("validation_results", {}), Mapping)
                else {}
            ),
            artifact_manifest=(
                dict(values.get("artifact_manifest", {}))
                if isinstance(values.get("artifact_manifest", {}), Mapping)
                else {}
            ),
        )


@dataclass(slots=True)
class BudgetSnapshot:
    """Normalized process-level snapshot shared by all Shiny sessions."""

    rows: pd.DataFrame
    generated_at: str
    latest_year: int
    years: tuple[int, ...]
    metadata: SnapshotMetadata
    status: SnapshotStatus = "fresh"
    status_message: str | None = None
    overview: pd.DataFrame | None = field(default=None, compare=False, repr=False)

    @property
    def data(self) -> pd.DataFrame:
        """Alias used by consumers that call the snapshot's dataframe ``data``."""

        return self.rows

    @property
    def stale(self) -> bool:
        return self.status == "stale"

    @property
    def data_updated_at(self) -> str:
        """Stable source update timestamp used by the persistent status shell."""

        return self.metadata.fetched_at

    @property
    def version(self) -> str:
        """Prepared bundle version, or an empty value for a legacy snapshot."""

        return self.metadata.version


@dataclass(frozen=True, slots=True)
class DrilldownNode:
    id: str
    parent_id: str | None
    level: str
    label: str
    current: float
    prior: float
    change: float
    percent_change: float | None
    line_items: int


@dataclass(frozen=True, slots=True)
class DrilldownModel:
    year: int
    compare_year: int | None
    flow: Flow
    scope: Scope
    scope_label: str
    root: DrilldownNode
    nodes: tuple[DrilldownNode, ...]


@dataclass(frozen=True, slots=True)
class ScenarioValidation:
    valid: bool
    balanced: bool
    total_delta: float
    errors: tuple[str, ...] = ()
    adjusted: pd.DataFrame | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class RepositoryResult:
    """Explicit repository status for UI freshness and error messaging."""

    snapshot: BudgetSnapshot | None
    status: SnapshotStatus
    message: str | None = None
    cache_source: CacheSource | None = None
    elapsed_ms: float | None = None


@dataclass(frozen=True, slots=True)
class RefreshStatus:
    """Observable process-wide refresh state, independent of active data."""

    state: Literal["idle", "running", "success", "unchanged", "error"] = "idle"
    started_at: str | None = None
    completed_at: str | None = None
    active_version: str | None = None
    message: str | None = None
    stage_timings_ms: Mapping[str, float] = field(default_factory=dict, compare=False)


@dataclass(frozen=True, slots=True)
class PreparedBudgetBundle:
    """Immutable, process-shareable prepared budget data.

    ``rows`` and aggregate frames are treated as read-only by contract.  Query
    helpers return narrow copies so a session cannot mutate process-wide data.
    """

    rows: pd.DataFrame
    snapshot: BudgetSnapshot
    choices: Mapping[str, Any] = field(default_factory=dict, compare=False)
    aggregates: Mapping[str, pd.DataFrame] = field(default_factory=dict, compare=False)
    indexes: Mapping[str, Mapping[Any, tuple[int, ...]]] = field(default_factory=dict, compare=False)
    record_counts: pd.DataFrame | None = field(default=None, compare=False, repr=False)

    @property
    def metadata(self) -> SnapshotMetadata:
        return self.snapshot.metadata

    @property
    def version(self) -> str:
        return self.metadata.version

    @property
    def data_updated_at(self) -> str:
        return self.metadata.fetched_at

    @property
    def latest_year(self) -> int:
        return self.snapshot.latest_year

    @property
    def years(self) -> tuple[int, ...]:
        return self.snapshot.years

    @property
    def data(self) -> pd.DataFrame:
        """Compatibility alias for consumers migrating from ``BudgetSnapshot``."""

        return self.rows

    @property
    def status(self) -> SnapshotStatus:
        return self.snapshot.status

    def query_rows(self, **filters: object) -> pd.DataFrame:
        """Return a narrow copy matching supported context filters."""

        result = self.rows
        for column, value in filters.items():
            if value is None or value in {"all", "all_funds"}:
                continue
            if column == "scope":
                column = "fund_scope"
            elif column == "year":
                column = "fiscal_year"
            elif column == "flow":
                column = "expense_revenue"
            if column not in result.columns:
                raise KeyError(f"Unsupported bundle filter: {column}")
            result = result.loc[result[column].eq(value)]
        return result.copy()

    def aggregate(self, name: str) -> pd.DataFrame:
        """Return a copy of a precomputed aggregate table by logical name."""

        aliases = {
            "department_totals": "hierarchy_department",
            "fund_totals": "hierarchy_fund",
            "category_totals": "hierarchy_category",
            "totals_yfs": "totals_by_year_flow_scope",
            "history_series": "history",
            "signals": "signals_department",
        }
        name = aliases.get(name, name)
        try:
            return self.aggregates[name].copy()
        except KeyError as exc:
            raise KeyError(f"Unknown prepared aggregate: {name}") from exc

    def hierarchy(
        self,
        dimension: str,
        *,
        year: int | None = None,
        flow: str | None = None,
        scope: str | None = None,
        department: str | None = None,
        fund: str | None = None,
    ) -> pd.DataFrame:
        """Query one long-form hierarchy table without recomputing groupbys."""

        table = self.aggregate(f"hierarchy_{dimension}")
        for column, value in (("fiscal_year", year), ("expense_revenue", flow), ("fund_scope", scope)):
            if value is None or value == "all":
                continue
            if column == "fund_scope" and value == "all_funds":
                table = table.loc[table[column].eq("all_funds")]
            elif value != "all_funds":
                table = table.loc[table[column].eq(value)]
        for column, value in (("department", department), ("fund", fund)):
            if value is not None and value not in {"all", "all_funds"} and column in table.columns:
                table = table.loc[table[column].eq(value)]
        return table.reset_index(drop=True)

    def choices_for(
        self,
        dimension: str,
        *,
        department: str | None = None,
        fund: str | None = None,
    ) -> tuple[str, ...]:
        """Return precomputed context-aware Explorer choices."""

        if dimension == "fund" and department:
            return tuple(self.choices.get(f"funds_by_department:{department}", ()))
        if dimension == "category" and department and fund:
            return tuple(self.choices.get(f"categories_by_department_fund:{department}\x1f{fund}", ()))
        return tuple(self.choices.get(dimension, ()))

    def record_count(self, **filters: object) -> int:
        """Return a record count for a supported hierarchy context."""

        if self.record_counts is None:
            return len(self.query_rows(**filters))
        aliases = {"year": "fiscal_year", "flow": "expense_revenue", "scope": "fund_scope"}
        table = self.record_counts
        for column, value in filters.items():
            column = aliases.get(column, column)
            if value is not None and value not in {"all", "all_funds"} and column in table.columns:
                table = table.loc[table[column].eq(value)]
        return int(table["line_items"].sum()) if not table.empty else 0

    def exact_rows(self, object_ids: int | list[int] | tuple[int, ...]) -> pd.DataFrame:
        """Return exact source records using the prepared object-id index."""

        ids = [object_ids] if isinstance(object_ids, int) else list(object_ids)
        positions: list[int] = []
        index = self.indexes.get("object_id", {})
        for object_id in ids:
            positions.extend(index.get(object_id, ()))
        return self.rows.iloc[positions].copy() if positions else self.rows.iloc[0:0].copy()
