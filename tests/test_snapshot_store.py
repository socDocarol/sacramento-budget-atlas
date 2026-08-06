from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
import pytest

from budget_app.config import Settings
from budget_app.data.models import RepositoryResult
from budget_app.data.prepared import PreparedBundleStore, prepare_bundle
from budget_app.data.store import SnapshotStore


def rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fiscal_year": 2027,
                "department": "Police",
                "fund": "General Fund",
                "category": "Personnel",
                "amount": 1.0,
                "expense_revenue": "Expenses",
                "fund_category": "Governmental Funds",
                "object_id": 1,
            }
        ]
    )


class FakeRepository:
    def __init__(self, cache_dir: Path, bundle_store: PreparedBundleStore) -> None:
        self.settings = Settings(
            arcgis_url="https://example.test",
            cache_dir=cache_dir,
            cache_ttl_seconds=0,
            log_level="INFO",
            app_base_path="/",
            allowed_hosts=("testserver",),
            manual_refresh_enabled=False,
            manual_refresh_cooldown_seconds=300,
        )
        self.bundle_store = bundle_store
        self.calls = 0
        self.result: RepositoryResult | None = None

    async def load_result(self, *, force: bool = False) -> RepositoryResult:
        self.calls += 1
        await asyncio.sleep(0.01)
        assert self.result is not None
        return self.result

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_concurrent_refresh_is_single_flight(tmp_path: Path) -> None:
    bundle_store = PreparedBundleStore(tmp_path)
    bundle = prepare_bundle(rows(), source_url="x", fetched_at="2026-01-01T00:00:00+00:00")
    bundle_store.promote(bundle)
    repository = FakeRepository(tmp_path, bundle_store)
    repository.result = RepositoryResult(bundle.snapshot, "fresh", cache_source="source")
    store = SnapshotStore(repository=repository, bundle_store=bundle_store)
    seen: list[str] = []
    store.subscribe(lambda value: seen.append(value.version))
    await asyncio.gather(store.refresh(force=True), store.refresh(force=True), store.refresh(force=True))
    assert repository.calls == 1
    assert store.active_bundle is not None
    assert seen == []
    assert store.status.state == "unchanged"


@pytest.mark.asyncio
async def test_refresh_failure_retains_active_bundle(tmp_path: Path) -> None:
    bundle_store = PreparedBundleStore(tmp_path)
    bundle = prepare_bundle(rows(), source_url="x", fetched_at="2026-01-01T00:00:00+00:00")
    bundle_store.promote(bundle)
    repository = FakeRepository(tmp_path, bundle_store)

    async def failing(*, force: bool = False) -> RepositoryResult:
        raise RuntimeError("offline")

    repository.load_result = failing  # type: ignore[method-assign]
    store = SnapshotStore(repository=repository, bundle_store=bundle_store)
    current = await store.refresh(force=True)
    assert current is not None
    assert current.version == bundle.version
    assert store.active_bundle is not None
    assert store.status.state == "error"
    assert store.status.active_version == bundle.version
