from __future__ import annotations

import re
from typing import Any

import pytest
from playwright.sync_api import Page, expect
from shiny.playwright import controller

pytestmark = pytest.mark.e2e


def ready(page: Page, url: str, status_class: str = ".city-source-status--fresh") -> None:
    page.goto(url, wait_until="domcontentloaded")
    expect(page.locator(status_class)).to_be_visible(timeout=30_000)


def source_is_ready(actual: Any) -> bool:
    return bool(
        isinstance(actual, dict)
        and actual.get("source_loading") is False
        and actual.get("source", {}).get("status") == "fresh"
        and actual.get("source", {}).get("row_count", 0) > 0
    )


def source_is_stale(actual: Any) -> bool:
    return bool(
        isinstance(actual, dict)
        and actual.get("source_loading") is False
        and actual.get("source", {}).get("status") == "stale"
        and actual.get("source", {}).get("cache_source") == "stale-disk"
        and actual.get("snapshot_stale") is True
    )


def drawer_has_exact_context(actual: Any) -> bool:
    detail = actual.get("detail_selection", {}) if isinstance(actual, dict) else {}
    return bool(actual.get("drawer_desired_open") is True and detail.get("department"))


def drawer_is_closed(actual: Any) -> bool:
    return bool(isinstance(actual, dict) and actual.get("drawer_desired_open") is False)


def overview_has_initial_state(actual: Any) -> bool:
    selection = actual.get("selection", {}) if isinstance(actual, dict) else {}
    return bool(
        actual.get("current_rows", 0) > 0
        and actual.get("history_rows", 0) > 0
        and selection
        == {
            "year": 2027,
            "compare_year": 2026,
            "flow": "all",
            "fund_scope": "all_funds",
            "department": None,
            "fund": None,
            "category": None,
            "selected_record": None,
        }
    )


def test_app_test_values_and_snapshot_preprocessors(page: Page, live_server_url: str) -> None:
    ready(page, live_server_url)
    values = controller.AppTestValues(page)
    values.expect_export("application_state", source_is_ready, timeout=30)
    values.expect_input("share_state", "<action-count>", timeout=20)
    values.expect_input("retry_source", "<action-count>", timeout=20)
    values.expect_export(
        "overview-test_state",
        overview_has_initial_state,
        timeout=30,
    )


def test_explorer_grid_controller_filter_sort_selection_and_exact_state(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    page.locator('[data-nav-value="explorer"]').first.click()
    expect(page).to_have_url(re.compile(r"#explorer$"))

    grid = controller.OutputDataFrame(page, "explorer-table")
    values = controller.AppTestValues(page)
    grid.expect_nrow(2000, timeout=30_000)
    grid.expect_ncol(9, timeout=20_000)
    grid.expect_column_labels(
        [
            "fiscal_year",
            "department",
            "fund",
            "category",
            "amount",
            "expense_revenue",
            "fund_category",
            "object_id",
            "fund_scope",
        ],
        timeout=20_000,
    )

    initial = values.get()["export"]["explorer-test_state"]
    department = initial["visible_departments"][0]

    def only_department_visible(actual: Any) -> bool:
        return bool(
            isinstance(actual, dict)
            and actual.get("visible_rows", 0) > 0
            and actual.get("visible_departments") == [department]
        )

    grid.set_filter({"col": 1, "value": department}, timeout=20_000)
    values.expect_export("explorer-test_state", only_department_visible, timeout=20)

    def object_ids_descending(actual: Any) -> bool:
        ids = actual.get("visible_object_ids", []) if isinstance(actual, dict) else []
        return bool(ids and ids == sorted(ids, reverse=True))

    grid.set_sort({"col": 7, "desc": True}, timeout=20_000)
    values.expect_export("explorer-test_state", object_ids_descending, timeout=20)
    grid.select_rows([0], timeout=20_000)
    grid.expect_selected_rows([0], timeout=20_000)
    grid.expect_selected_num_rows(1, timeout=20_000)

    def one_exact_record_selected(actual: Any) -> bool:
        selected = actual.get("selected_object_ids", []) if isinstance(actual, dict) else []
        visible = actual.get("visible_object_ids", []) if isinstance(actual, dict) else []
        return bool(len(selected) == 1 and visible and selected[0] == visible[0])

    values.expect_export("explorer-test_state", one_exact_record_selected, timeout=20)
    selected_state = values.get()["export"]["explorer-test_state"]
    selected_object_id = selected_state["selected_object_ids"][0]
    expect(page.locator("#explorer-detail")).to_contain_text(f"ObjectId {selected_object_id}")
    expect(page.locator('.city-detail-drawer[role="dialog"]')).to_be_visible(timeout=20_000)


def test_what_changed_plotly_marks_coordinate_drawer_state(page: Page, live_server_url: str) -> None:
    ready(page, live_server_url)
    values = controller.AppTestValues(page)
    page.locator('[data-nav-value="changed"]').first.click()
    expect(page).to_have_url(re.compile(r"#changed$"))

    bar = page.locator("#changed-chart .barlayer path").first
    expect(bar).to_be_visible(timeout=30_000)
    bar.click(force=True)
    values.expect_export("application_state", drawer_has_exact_context, timeout=20)
    page.locator("[data-detail-close]").first.click()
    values.expect_export("application_state", drawer_is_closed, timeout=20)
    expect(page.locator("[data-detail-overlay]")).to_have_attribute(
        "data-detail-lifecycle",
        "closed",
        timeout=20_000,
    )

    point = page.locator("#changed-scatter .scatterlayer .point").first
    expect(point).to_be_visible(timeout=30_000)
    point.click(force=True)
    values.expect_export("application_state", drawer_has_exact_context, timeout=20)


def test_stale_cache_path_is_visible_and_exported(page: Page, stale_server_url: str) -> None:
    ready(page, stale_server_url, ".city-source-status--warning")
    expect(page.locator(".city-source-status--warning")).to_contain_text(
        "Serving the last successful", timeout=20_000
    )
    controller.AppTestValues(page).expect_export(
        "application_state",
        source_is_stale,
        timeout=30,
    )


def test_production_startup_does_not_serve_test_snapshots(
    page: Page, production_mode_server_url: str
) -> None:
    ready(page, production_mode_server_url)
    snapshot_url = page.wait_for_function(
        "() => window.Shiny?.shinyapp?.getTestSnapshotBaseUrl?.({ fullUrl: true }) ?? false",
        timeout=20_000,
    ).json_value()
    response = page.request.get(str(snapshot_url))
    assert response.status == 404
