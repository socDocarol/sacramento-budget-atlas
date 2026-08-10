from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest

from budget_app.data import PreparedBundleStore, prepare_bundle
from budget_app.data.domain import aggregate_by_dimension, overview_totals
from budget_app.data.models import SnapshotMetadata


def rows(amount: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fiscal_year": 2026,
                "department": "Police",
                "fund": "General Fund",
                "category": "Personnel",
                "amount": amount,
                "expense_revenue": "Expenses",
                "fund_category": "Governmental Funds",
                "object_id": 1,
            },
            {
                "fiscal_year": 2027,
                "department": "Parks",
                "fund": "Measure U Fund",
                "category": "Programs",
                "amount": 2.0,
                "expense_revenue": "Expenses",
                "fund_category": "Governmental Funds",
                "object_id": 2,
            },
        ]
    )


def test_bundle_precomputes_context_and_matches_domain() -> None:
    bundle = prepare_bundle(
        rows(),
        source_url="https://example.test",
        source_last_edit_date=7,
        fetched_at="2026-01-01T00:00:00+00:00",
    )
    assert "fund_scope" in bundle.rows
    assert bundle.metadata.content_hash
    assert bundle.metadata.checked_at
    assert bundle.metadata.prepared_at
    assert bundle.metadata.validation_results["content_hash"] is True
    assert bundle.choices_for("fund", department="Police") == ("General Fund",)
    assert bundle.choices_for("category", department="Police", fund="General Fund") == ("Personnel",)
    assert bundle.record_count(year=2026, department="Police") == 1
    assert bundle.exact_rows(1)["department"].tolist() == ["Police"]
    expected = aggregate_by_dimension(rows(), "department", year=2026, flow="Expenses")
    actual = bundle.hierarchy("department", year=2026, flow="Expenses", scope="all_funds")
    pd.testing.assert_frame_equal(
        actual[["name", "amount", "share", "line_items"]].reset_index(drop=True),
        expected.reset_index(drop=True),
        check_dtype=False,
    )
    pd.testing.assert_frame_equal(
        bundle.aggregate("overview_totals"), overview_totals(rows()), check_dtype=False
    )
    fund_context = bundle.hierarchy("fund", year=2026, flow="Expenses", department="Police")
    assert fund_context.iloc[0]["name"] == "General Fund"
    assert bundle.record_count(scope="all_funds", year=2026) == 1


def test_versioned_promotion_and_corruption_fallback(tmp_path: Path) -> None:
    store = PreparedBundleStore(tmp_path)
    first = store.promote(prepare_bundle(rows(1.0), source_url="x", fetched_at="2026-01-01T00:00:00+00:00"))
    second = store.promote(prepare_bundle(rows(3.0), source_url="x", fetched_at="2026-01-02T00:00:00+00:00"))
    assert first.version != second.version
    assert json.loads((tmp_path / "current.json").read_text())["version"] == second.version
    (tmp_path / "snapshots" / second.version / "rows.parquet").write_bytes(b"corrupt")
    loaded = store.load_current()
    assert loaded is not None
    assert loaded.version == first.version
    assert loaded.data_updated_at == "2026-01-01T00:00:00+00:00"


def test_legacy_migration_preserves_timestamp_and_pair(tmp_path: Path) -> None:
    frame = rows()
    frame.to_parquet(tmp_path / "approved-budgets.parquet", index=False)
    metadata = SnapshotMetadata(
        source_url="legacy",
        source_last_edit_date=11,
        generated_at="2026-01-01T00:00:00+00:00",
        fetched_at="2025-12-01T00:00:00+00:00",
        row_count=len(frame),
        years=(2026, 2027),
    )
    (tmp_path / "approved-budgets.metadata.json").write_text(json.dumps(metadata.as_dict()))
    bundle = PreparedBundleStore(tmp_path).load_current()
    assert bundle is not None
    assert bundle.data_updated_at == metadata.fetched_at
    assert (tmp_path / "approved-budgets.parquet").exists()
    assert (tmp_path / "approved-budgets.metadata.json").exists()
    assert (tmp_path / "current.json").exists()


def test_artifact_hash_detects_aggregate_or_choice_corruption(tmp_path: Path) -> None:
    store = PreparedBundleStore(tmp_path)
    bundle = store.promote(prepare_bundle(rows(), source_url="x"))
    aggregate_path = next((tmp_path / "snapshots" / bundle.version / "aggregates").glob("*.parquet"))
    aggregate_path.write_bytes(aggregate_path.read_bytes() + b"x")
    assert store.load_current() is None

    repaired = store.promote(prepare_bundle(rows(), source_url="x"))
    choices_path = tmp_path / "snapshots" / repaired.version / "choices.json"
    choices_path.write_text("{}", encoding="utf-8")
    assert store.load_current() is None


def test_concurrent_promotions_are_serialized_and_leave_valid_pointer(tmp_path: Path) -> None:
    bundles = [
        prepare_bundle(rows(amount), source_url="x", fetched_at=f"2026-01-0{index}T00:00:00+00:00")
        for index, amount in enumerate((2.0, 3.0), start=1)
    ]

    def promote(bundle):
        return PreparedBundleStore(tmp_path).promote(bundle)

    with ThreadPoolExecutor(max_workers=2) as executor:
        promoted = list(executor.map(promote, bundles))

    assert {bundle.version for bundle in promoted} == {bundle.version for bundle in bundles}
    current = PreparedBundleStore(tmp_path).load_current()
    assert current is not None
    assert current.version in {bundle.version for bundle in bundles}
    assert not list(tmp_path.glob(".current-*.json.tmp"))
    assert not list((tmp_path / "snapshots").glob(".staging-*"))


def test_promotion_lock_times_out_without_changing_current(tmp_path: Path) -> None:
    store = PreparedBundleStore(tmp_path)
    first = store.promote(prepare_bundle(rows(1.0), source_url="x"))
    contender = PreparedBundleStore(tmp_path, promotion_lock_timeout=0.05)

    with store._promotion_lock(), pytest.raises(TimeoutError, match="promotion lock"):
        contender.promote(prepare_bundle(rows(4.0), source_url="x"))

    assert PreparedBundleStore(tmp_path).load_current().version == first.version


def test_cache_paths_reject_pointer_and_manifest_traversal(tmp_path: Path) -> None:
    store = PreparedBundleStore(tmp_path)
    bundle = store.promote(prepare_bundle(rows(), source_url="x"))
    outside = tmp_path / "outside"
    outside.mkdir()

    assert store.load_version("../outside") is None
    (tmp_path / "current.json").write_text(json.dumps({"version": "../outside"}), encoding="utf-8")
    assert store.load_current().version == bundle.version

    metadata_path = tmp_path / "snapshots" / bundle.version / "bundle.metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["artifact_manifest"]["../outside"] = {"sha256": "invalid", "size": 0}
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert store.load_version(bundle.version) is None

    repaired = store.promote(prepare_bundle(rows(), source_url="x"))
    metadata_path = tmp_path / "snapshots" / repaired.version / "bundle.metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["aggregate_manifest"]["overview_totals"] = "../../outside.parquet"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert store.load_version(repaired.version) is None


def test_retention_keeps_current_and_recent_valid_fallbacks(tmp_path: Path) -> None:
    store = PreparedBundleStore(tmp_path, retained_versions=3)
    versions = []
    for index in range(5):
        bundle = store.promote(
            prepare_bundle(
                rows(float(index + 1)),
                source_url="x",
                fetched_at=f"2026-01-0{index + 1}T00:00:00+00:00",
            )
        )
        versions.append(bundle.version)

    remaining = {path.name for path in (tmp_path / "snapshots").iterdir() if path.is_dir()}
    assert remaining == set(versions[-3:])
    assert json.loads((tmp_path / "current.json").read_text())["version"] == versions[-1]


def test_failed_promotion_preserves_current_and_fallback(tmp_path: Path, monkeypatch) -> None:
    store = PreparedBundleStore(tmp_path)
    first = store.promote(prepare_bundle(rows(1.0), source_url="x"))
    second = store.promote(prepare_bundle(rows(2.0), source_url="x"))

    def fail_write(directory, bundle):
        raise OSError("simulated write failure")

    monkeypatch.setattr(store, "_write_bundle_files", fail_write)
    with pytest.raises(OSError, match="simulated write failure"):
        store.promote(prepare_bundle(rows(5.0), source_url="x"))

    assert json.loads((tmp_path / "current.json").read_text())["version"] == second.version
    assert store.load_current().version == second.version
    assert (tmp_path / "snapshots" / first.version).exists()
    assert not list((tmp_path / "snapshots").glob(".staging-*"))
