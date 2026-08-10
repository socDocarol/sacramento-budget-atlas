from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from budget_app.config import Settings as AppSettings
from budget_app.data.repository import (
    _MEMORY_CACHE,
    ArcGISBudgetRepository,
    SnapshotUnavailableError,
)


def make_settings(
    *,
    arcgis_url: str,
    cache_dir: Path,
    cache_ttl_seconds: int,
    log_level: str,
    app_base_path: str,
    prepared_schema_version: int = 1,
) -> AppSettings:
    return AppSettings(
        arcgis_url=arcgis_url,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        log_level=log_level,
        app_base_path=app_base_path,
        allowed_hosts=("testserver",),
        manual_refresh_enabled=False,
        manual_refresh_cooldown_seconds=300,
        prepared_schema_version=prepared_schema_version,
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
    settings = make_settings(
        arcgis_url="https://example.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=86400,
        log_level="INFO",
        app_base_path="/",
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(return_value=httpx.Response(200, json={"lastEditDate": 10}))

        def query(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("returnCountOnly") == "true":
                return httpx.Response(200, json={"count": 2})
            offset = int(request.url.params.get("resultOffset", "0"))
            if offset == 0:
                return httpx.Response(
                    200, json={"features": [source_feature(1)], "exceededTransferLimit": True}
                )
            return httpx.Response(200, json={"features": [source_feature(2)]})

        query_route = router.get(f"{settings.arcgis_url}/query").mock(side_effect=query)
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
    page_requests = [
        call.request for call in query_route.calls if call.request.url.params.get("returnCountOnly") != "true"
    ]
    count_requests = [
        call.request for call in query_route.calls if call.request.url.params.get("returnCountOnly") == "true"
    ]
    assert len(count_requests) == 1
    assert len(page_requests) == 2
    assert page_requests[0].url.params["outFields"] == (
        "Fiscal_Year,Department,Fund,CATEGORY,Amount,ExpenseRevenue,Fund_Category,ObjectId"
    )
    assert page_requests[0].url.params["returnGeometry"] == "false"
    assert (tmp_path / "approved-budgets.parquet").exists()
    assert json.loads((tmp_path / "approved-budgets.metadata.json").read_text())["row_count"] == 2


@pytest.mark.asyncio
async def test_repository_returns_stale_cache_on_refresh_failure(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = make_settings(
        arcgis_url="https://stale.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=1,
        log_level="INFO",
        app_base_path="/",
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(return_value=httpx.Response(200, json={"lastEditDate": 10}))
        router.get(f"{settings.arcgis_url}/query").mock(
            side_effect=lambda request: httpx.Response(
                200,
                json=(
                    {"count": 1}
                    if request.url.params.get("returnCountOnly") == "true"
                    else {"features": [source_feature(1)]}
                ),
            )
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
    settings = make_settings(
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
            if request.url.params.get("returnCountOnly") == "true":
                return httpx.Response(200, json={"count": 1000})
            offset = int(request.url.params.get("resultOffset", "0"))
            if offset == 0:
                return httpx.Response(200, json={"features": full_page})
            return httpx.Response(200, json={"features": []})

        query_route = router.get(f"{settings.arcgis_url}/query").mock(side_effect=query)
        snapshot = await ArcGISBudgetRepository(settings).load_snapshot()
    assert len(snapshot.rows) == 1000
    page_requests = [
        call.request for call in query_route.calls if call.request.url.params.get("returnCountOnly") != "true"
    ]
    assert len(page_requests) == 2


@pytest.mark.asyncio
async def test_repository_reports_no_snapshot_when_source_fails(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = make_settings(
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
    settings = make_settings(
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
                200,
                json=(
                    {"count": 1}
                    if request.url.params.get("returnCountOnly") == "true"
                    else {"features": [source_feature(1, amount["value"])]}
                ),
            )
        )
        repository = ArcGISBudgetRepository(settings)
        first = await repository.load_result(force=True)
        first_snapshot = first.snapshot
        assert first_snapshot is not None
        assert query_route.call_count == 2
        unchanged = await repository.load_result(force=True)
        assert unchanged.snapshot is not None
        assert unchanged.snapshot.version == first_snapshot.version
        assert unchanged.snapshot.data_updated_at == first_snapshot.data_updated_at
        assert query_route.call_count == 2

        metadata["value"] = 11
        amount["value"] = 2.0
        changed = await repository.load_result(force=True)
        assert changed.snapshot is not None
        assert changed.snapshot.version != first_snapshot.version
        assert changed.snapshot.data_updated_at != first_snapshot.data_updated_at
        assert query_route.call_count == 4


@pytest.mark.asyncio
async def test_repository_rejects_incomplete_pagination(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = make_settings(
        arcgis_url="https://incomplete.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=0,
        log_level="INFO",
        app_base_path="/",
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(return_value=httpx.Response(200, json={"lastEditDate": 10}))
        router.get(f"{settings.arcgis_url}/query").mock(
            side_effect=lambda request: httpx.Response(
                200,
                json=(
                    {"count": 2}
                    if request.url.params.get("returnCountOnly") == "true"
                    else {"features": [source_feature(1)]}
                ),
            )
        )
        with pytest.raises(SnapshotUnavailableError, match="pagination was incomplete"):
            await ArcGISBudgetRepository(settings).load_snapshot(force=True)


@pytest.mark.asyncio
async def test_repository_rejects_duplicate_object_ids(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = make_settings(
        arcgis_url="https://duplicates.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=0,
        log_level="INFO",
        app_base_path="/",
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(return_value=httpx.Response(200, json={"lastEditDate": 10}))
        router.get(f"{settings.arcgis_url}/query").mock(
            side_effect=lambda request: httpx.Response(
                200,
                json=(
                    {"count": 2}
                    if request.url.params.get("returnCountOnly") == "true"
                    else {"features": [source_feature(1), source_feature(1)]}
                ),
            )
        )
        with pytest.raises(SnapshotUnavailableError, match="duplicate ObjectIds"):
            await ArcGISBudgetRepository(settings).load_snapshot(force=True)


@pytest.mark.asyncio
async def test_repository_retries_when_source_changes_during_fetch(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = make_settings(
        arcgis_url="https://changing.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=0,
        log_level="INFO",
        app_base_path="/",
    )
    edits = iter((10, 11, 11, 11))
    with respx.mock(assert_all_called=False) as router:
        metadata_route = router.get(settings.arcgis_url).mock(
            side_effect=lambda request: httpx.Response(200, json={"lastEditDate": next(edits)})
        )
        query_route = router.get(f"{settings.arcgis_url}/query").mock(
            side_effect=lambda request: httpx.Response(
                200,
                json=(
                    {"count": 1}
                    if request.url.params.get("returnCountOnly") == "true"
                    else {"features": [source_feature(1)]}
                ),
            )
        )
        snapshot = await ArcGISBudgetRepository(settings).load_snapshot(force=True)

    assert snapshot.metadata.source_last_edit_date == 11
    assert metadata_route.call_count == 4
    assert query_route.call_count == 4


@pytest.mark.asyncio
async def test_repository_bounds_source_change_retries(tmp_path: Path) -> None:
    _MEMORY_CACHE.clear()
    settings = make_settings(
        arcgis_url="https://always-changing.test/FeatureServer/0",
        cache_dir=tmp_path,
        cache_ttl_seconds=0,
        log_level="INFO",
        app_base_path="/",
    )
    edit = {"value": 0}

    def metadata(_request: httpx.Request) -> httpx.Response:
        edit["value"] += 1
        return httpx.Response(200, json={"lastEditDate": edit["value"]})

    with respx.mock(assert_all_called=False) as router:
        router.get(settings.arcgis_url).mock(side_effect=metadata)
        query_route = router.get(f"{settings.arcgis_url}/query").mock(
            side_effect=lambda request: httpx.Response(
                200,
                json=(
                    {"count": 1}
                    if request.url.params.get("returnCountOnly") == "true"
                    else {"features": [source_feature(1)]}
                ),
            )
        )
        with pytest.raises(SnapshotUnavailableError, match="after 3 attempts"):
            await ArcGISBudgetRepository(settings).load_snapshot(force=True)

    assert query_route.call_count == 6
