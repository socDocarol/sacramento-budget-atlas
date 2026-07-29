from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from budget_app.config import Settings
from budget_app.data.repository import (
    _MEMORY_CACHE,
    ArcGISBudgetRepository,
    SnapshotUnavailableError,
)


def source_feature(object_id: int, amount: float = 1.0) -> dict[str, object]:
    return {
        "attributes": {
            "Fiscal_Year": 2027,
            "Department": "Police",
            "Fund": "General Fund",
            "CATEGORY": "Personnel",
            "Amount": amount,
            "ExpenseRevenue": "Expenses",
            "Fund_Category": "Governmental Funds",
            "ObjectId": object_id,
        }
    }


@pytest.mark.asyncio
async def test_repository_paginates_and_writes_atomic_cache(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = Settings(
        arcgis_url="https://example.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=86400,
        log_level="INFO",
        app_base_path="/",
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(return_value=httpx.Response(200, json={"lastEditDate": 10}))

        def query(request: httpx.Request) -> httpx.Response:
            offset = int(request.url.params.get("resultOffset", "0"))
            if offset == 0:
                return httpx.Response(
                    200, json={"features": [source_feature(1)], "exceededTransferLimit": True}
                )
            return httpx.Response(200, json={"features": [source_feature(2)]})

        router.get(f"{settings.arcgis_url}/query").mock(side_effect=query)
        repository = ArcGISBudgetRepository(settings)
        result = await repository.load_result()
        assert result.cache_source == "source"
        assert result.elapsed_ms is not None and result.elapsed_ms > 0
        snapshot = result.snapshot
        assert snapshot is not None
        memory_result = await repository.load_result()
        assert memory_result.cache_source == "memory"
        _MEMORY_CACHE.clear()
        disk_result = await ArcGISBudgetRepository(settings).load_result()
        assert disk_result.cache_source == "disk-fresh"
    assert snapshot.rows["object_id"].tolist() == [1, 2]
    assert (tmp_path / "approved-budgets.parquet").exists()
    assert json.loads((tmp_path / "approved-budgets.metadata.json").read_text())["row_count"] == 2


@pytest.mark.asyncio
async def test_repository_returns_stale_cache_on_refresh_failure(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = Settings(
        arcgis_url="https://stale.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=1,
        log_level="INFO",
        app_base_path="/",
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(return_value=httpx.Response(200, json={"lastEditDate": 10}))
        router.get(f"{settings.arcgis_url}/query").mock(
            return_value=httpx.Response(200, json={"features": [source_feature(1)]})
        )
        repository = ArcGISBudgetRepository(settings)
        await repository.load_snapshot()
    _MEMORY_CACHE.clear()
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(side_effect=httpx.ConnectError("offline"))
        router.get(f"{settings.arcgis_url}/query").mock(side_effect=httpx.ConnectError("offline"))
        result = await ArcGISBudgetRepository(settings).load_result(force=True)
    assert result.status == "stale"
    assert result.cache_source == "stale-disk"
    assert result.elapsed_ms is not None and result.elapsed_ms > 0
    assert result.snapshot is not None and result.snapshot.stale


@pytest.mark.asyncio
async def test_repository_probes_after_full_terminal_page(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = Settings(
        arcgis_url="https://probe.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=86400,
        log_level="INFO",
        app_base_path="/",
    )
    full_page = [source_feature(index) for index in range(1, 1001)]
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(return_value=httpx.Response(200, json={"lastEditDate": 10}))

        def query(request: httpx.Request) -> httpx.Response:
            offset = int(request.url.params.get("resultOffset", "0"))
            if offset == 0:
                return httpx.Response(200, json={"features": full_page})
            return httpx.Response(200, json={"features": []})

        query_route = router.get(f"{settings.arcgis_url}/query").mock(side_effect=query)
        snapshot = await ArcGISBudgetRepository(settings).load_snapshot()
    assert len(snapshot.rows) == 1000
    assert query_route.call_count == 2


@pytest.mark.asyncio
async def test_repository_reports_no_snapshot_when_source_fails(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = Settings(
        arcgis_url="https://empty.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=1,
        log_level="INFO",
        app_base_path="/",
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(side_effect=httpx.ConnectError("offline"))
        router.get(f"{settings.arcgis_url}/query").mock(side_effect=httpx.ConnectError("offline"))
        with pytest.raises(SnapshotUnavailableError):
            await ArcGISBudgetRepository(settings).load_snapshot(force=True)


@pytest.mark.asyncio
async def test_source_version_and_timestamp_change_only_on_changed_rows(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = Settings(
        arcgis_url="https://version.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=0,
        log_level="INFO",
        app_base_path="/",
    )
    metadata = {"value": 10}
    amount = {"value": 1.0}

    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(
            side_effect=lambda request: httpx.Response(200, json={"lastEditDate": metadata["value"]})
        )
        query_route = router.get(f"{settings.arcgis_url}/query").mock(
            side_effect=lambda request: httpx.Response(
                200, json={"features": [source_feature(1, amount["value"])]}
            )
        )
        repository = ArcGISBudgetRepository(settings)
        first = await repository.load_result(force=True)
        first_snapshot = first.snapshot
        assert first_snapshot is not None
        assert query_route.call_count == 1
        unchanged = await repository.load_result(force=True)
        assert unchanged.snapshot is not None
        assert unchanged.snapshot.version == first_snapshot.version
        assert unchanged.snapshot.data_updated_at == first_snapshot.data_updated_at
        assert query_route.call_count == 1

        metadata["value"] = 11
        amount["value"] = 2.0
        changed = await repository.load_result(force=True)
        assert changed.snapshot is not None
        assert changed.snapshot.version != first_snapshot.version
        assert changed.snapshot.data_updated_at != first_snapshot.data_updated_at
        assert query_route.call_count == 2
