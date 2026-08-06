from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def ready(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded")
    expect(page.locator(".city-source-status--fresh")).to_be_visible(timeout=30_000)


def assert_no_horizontal_overflow(page: Page) -> None:
    assert page.evaluate("document.documentElement.scrollWidth === document.documentElement.clientWidth")


def test_navigation_shell_history_and_responsive_width(page: Page, live_server_url: str) -> None:
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "console",
        lambda message: console_errors.append(message.text) if message.type == "error" else None,
    )
    ready(page, live_server_url)
    expect(page.locator("main")).to_have_count(1)
    expect(page.locator("meta[name=robots]")).to_have_attribute("content", "noindex, nofollow")
    expect(page.get_by_role("button", name="Refresh source")).to_be_visible(timeout=20_000)
    assert_no_horizontal_overflow(page)

    primary_links = page.locator(".city-nav > .city-nav__link")
    expect(primary_links).to_have_text(["Overview", "What Changed", "Explorer", "Lab"])
    expect(page.locator(".city-resources > .city-resources__summary")).to_have_text("Resources")
    expect(page.locator(".city-resources__link")).to_have_text(["Budget 101", "Sources & Methods"])
    expect(page.locator('[data-nav-value="drilldown"]')).to_have_count(0)

    page.locator('[data-nav-value="changed"]').first.click()
    expect(page).to_have_url(re.compile(r"#changed$"))
    expect(page.get_by_role("heading", name="What changed between years?")).to_be_visible()

    page.locator('[data-nav-value="explorer"]').first.click()
    expect(page).to_have_url(re.compile(r"#explorer$"))
    expect(page.get_by_role("heading", name="Explorer")).to_be_visible()
    assert_no_horizontal_overflow(page)

    page.go_back()
    expect(page).to_have_url(re.compile(r"#changed$"))
    expect(page.get_by_role("heading", name="What changed between years?")).to_be_visible()
    page.go_forward()
    expect(page).to_have_url(re.compile(r"#explorer$"))
    expect(page.get_by_role("heading", name="Explorer")).to_be_visible()
    assert page_errors == []
    assert console_errors == []


def test_repeated_navigation_does_not_duplicate_history(page: Page, live_server_url: str) -> None:
    ready(page, live_server_url)
    page.locator('[data-nav-value="explorer"]').first.click()
    expect(page).to_have_url(re.compile(r"#explorer$"))
    history_length = page.evaluate("window.history.length")

    page.locator('[data-nav-value="explorer"]').first.click()
    expect(page).to_have_url(re.compile(r"#explorer$"))
    expect(page.get_by_role("heading", name="Explorer")).to_be_visible()
    assert page.evaluate("window.history.length") == history_length


def test_rapid_navigation_settles_final_view_without_extra_history_entries(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    initial_history = page.evaluate("window.history.length")

    for value in ("changed", "explorer", "lab"):
        page.locator(f'[data-nav-value="{value}"]').first.click()

    expect(page).to_have_url(re.compile(r"#lab$"), timeout=20_000)
    expect(page.locator('.city-nav__link[data-nav-value="lab"]')).to_have_class(
        re.compile(r"\bis-active\b"), timeout=20_000
    )
    expect(page.get_by_role("heading", name="Lab")).to_be_visible(timeout=20_000)
    assert page.evaluate("window.history.length") == initial_history + 3


def test_overview_reset_clears_one_action_context_and_linked_selection(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    movement = page.locator(".city-movement[data-overview-select]").first
    department = movement.get_attribute("data-selection-department")
    assert department
    movement.click()
    expect(page.locator('.city-detail-drawer[role="dialog"]')).to_be_visible(timeout=20_000)
    page.keyboard.press("Escape")
    selected = page.locator(f'.city-movement[data-selection-department="{department}"]')
    expect(selected).to_have_class(re.compile(r"\bis-selected\b"), timeout=20_000)

    page.locator("#overview-reset").click()
    expect(page.locator("#overview-flow")).to_have_value("all", timeout=20_000)
    expect(page.locator("#overview-fund_scope")).to_have_value("all_funds", timeout=20_000)
    expect(selected).not_to_have_class(re.compile(r"\bis-selected\b"), timeout=20_000)


def test_explorer_reset_returns_all_filters(page: Page, live_server_url: str) -> None:
    ready(page, live_server_url)
    page.locator('[data-nav-value="explorer"]').first.click()
    expect(page.locator("#explorer-table")).to_be_visible(timeout=20_000)
    page.locator("#explorer-department").select_option(index=1)
    expect(page.locator("#explorer-fund option").nth(1)).to_be_attached(timeout=20_000)
    page.locator("#explorer-fund").select_option(index=1)
    expect(page.locator("#explorer-category option").nth(1)).to_be_attached(timeout=20_000)
    page.locator("#explorer-category").select_option(index=1)

    page.locator("#explorer-reset").click()
    expect(page.locator("#explorer-department")).to_have_value("all", timeout=20_000)
    expect(page.locator("#explorer-fund")).to_have_value("all", timeout=20_000)
    expect(page.locator("#explorer-category")).to_have_value("all", timeout=20_000)


def test_detail_drawer_focus_escape_and_workspace_hierarchy(page: Page, live_server_url: str) -> None:
    ready(page, live_server_url)
    movement = page.locator(".city-movement").first
    movement.click()

    drawer = page.locator('.city-detail-drawer[role="dialog"]')
    expect(drawer).to_be_visible(timeout=20_000)
    expect(drawer).to_have_attribute("aria-modal", "true")
    expect(drawer.locator("[data-detail-close]").first).to_be_focused()

    page.keyboard.press("Escape")
    expect(drawer).to_be_hidden(timeout=20_000)
    expect(movement).to_be_focused(timeout=20_000)

    movement.click()
    expect(drawer).to_be_visible(timeout=20_000)
    drawer.locator("[data-detail-expand]").click()
    workspace = page.locator("#overview-analysis-workspace")
    expect(workspace).to_be_visible(timeout=20_000)
    expect(workspace).to_be_focused(timeout=20_000)

    department = page.locator("#overview-workspace_department")
    fund = page.locator("#overview-workspace_fund")
    category = page.locator("#overview-workspace_category")
    department.select_option(label="Public Works")
    expect(fund.locator('option[value="General Fund"]')).to_have_count(1, timeout=20_000)
    fund.select_option(label="General Fund")
    expect(category.locator('option[value="Services & Supplies"]')).to_have_count(1, timeout=20_000)
    category.select_option(label="Services & Supplies")
    breadcrumb = page.locator(".city-workspace-breadcrumb")
    expect(breadcrumb).to_contain_text("Public Works", timeout=20_000)
    expect(breadcrumb).to_contain_text("General Fund", timeout=20_000)
    expect(breadcrumb).to_contain_text("Services & Supplies", timeout=20_000)


def test_overview_bookmark_round_trip_restores_exact_shared_state(page: Page, live_server_url: str) -> None:
    ready(page, live_server_url)
    page.locator("#overview-flow").select_option("expense")
    expect(page.locator("#overview-flow")).to_have_value("expense")
    year = page.locator("#overview-year").input_value()
    compare = page.locator("#overview-compare").input_value()
    flow = page.locator("#overview-flow").input_value()
    scope = page.locator("#overview-fund_scope").input_value()

    page.locator(".city-movement").first.click()
    page.locator("[data-detail-expand]").click()
    workspace = page.locator("#overview-analysis-workspace")
    expect(workspace).to_be_visible(timeout=20_000)
    page.locator("#overview-workspace_department").select_option(label="Public Works")
    expect(page.locator('#overview-workspace_fund option[value="General Fund"]')).to_have_count(
        1, timeout=20_000
    )
    page.locator("#overview-workspace_fund").select_option(label="General Fund")
    expect(page.locator(".city-workspace-breadcrumb")).to_contain_text("General Fund", timeout=20_000)
    expect(page.locator('#overview-workspace_category option[value="Services & Supplies"]')).to_have_count(
        1, timeout=20_000
    )
    page.locator("#overview-workspace_category").select_option(label="Services & Supplies")
    expect(page.locator(".city-workspace-breadcrumb")).to_contain_text("Services & Supplies", timeout=20_000)

    page.locator("#share_state").click()
    expect(page).to_have_url(re.compile(r"_inputs_"), timeout=20_000)
    bookmarked = page.url
    bookmark_keys = set(parse_qs(urlsplit(bookmarked).query, keep_blank_values=True))
    assert len(bookmarked) < 2048
    assert not any(key.endswith(("_data_view_rows", "_data_view_indices")) for key in bookmark_keys)
    assert not bookmark_keys.intersection(
        {
            "share_state",
            "retry_source",
            "changed-reset",
            "explorer-reset",
            "explorer-copy_state",
            "overview-reset",
            "detail_reopen_request",
        }
    )

    restored = page.context.new_page()
    restored.goto(bookmarked, wait_until="domcontentloaded")
    expect(restored.locator(".city-source-status--fresh")).to_be_visible(timeout=30_000)
    expect(restored).to_have_url(re.compile(r"#overview$"), timeout=20_000)
    expect(restored.locator("#overview-year")).to_have_value(year, timeout=20_000)
    expect(restored.locator("#overview-compare")).to_have_value(compare, timeout=20_000)
    expect(restored.locator("#overview-flow")).to_have_value(flow, timeout=20_000)
    expect(restored.locator("#overview-fund_scope")).to_have_value(scope, timeout=20_000)
    expect(restored.locator("#overview-analysis-workspace")).to_be_visible(timeout=20_000)
    expect(restored.locator("#overview-workspace_department")).to_have_value("Public Works", timeout=20_000)
    expect(restored.locator("#overview-workspace_fund")).to_have_value("General Fund", timeout=20_000)
    expect(restored.locator("#overview-workspace_category")).to_have_value(
        "Services & Supplies", timeout=20_000
    )
    restored.close()


def test_skip_link_keeps_main_anchor_focus_and_invalid_hash_canonicalizes(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    page.keyboard.press("Tab")
    expect(page.locator(".skip-link")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page).to_have_url(re.compile(r"#main$"))
    expect(page.locator("#main")).to_be_focused()
    assert page.evaluate("window.scrollY > 0")

    page.goto(f"{live_server_url}/#bogus", wait_until="domcontentloaded")
    expect(page.locator(".city-source-status--fresh")).to_be_visible(timeout=30_000)
    expect(page).to_have_url(re.compile(r"#overview$"), timeout=20_000)
    expect(page.locator('.city-nav__link[data-nav-value="overview"]')).to_have_class(
        re.compile(r"\bis-active\b")
    )


def test_explorer_export_and_lab_validation(page: Page, live_server_url: str) -> None:
    ready(page, live_server_url)
    page.locator('[data-nav-value="explorer"]').first.click()
    expect(page.locator("#explorer-table")).to_be_visible(timeout=20_000)
    assert_no_horizontal_overflow(page)
    page.locator("#explorer-table tbody tr").first.click()
    expect(page.locator("#explorer-detail")).to_contain_text("Selected source record")
    expect(page.locator('.city-detail-drawer[role="dialog"]')).to_be_visible(timeout=20_000)
    page.keyboard.press("Escape")
    expect(page.locator('.city-detail-drawer[role="dialog"]')).to_be_hidden(timeout=20_000)
    with page.expect_download() as download_info:
        page.locator("#explorer-download").click()
    assert download_info.value.suggested_filename == "sacramento-budget-explorer.csv"

    page.locator('[data-nav-value="lab"]').first.click()
    expect(page.get_by_role("heading", name="Lab")).to_be_visible()
    page.locator("#lab-department_1").select_option(index=1)
    page.locator("#lab-adjustment_1").fill("100000")
    page.locator("#lab-adjustment_1").press("Tab")
    expect(page.get_by_text("Balanced scenarios must net to zero")).to_be_visible()


def test_explorer_drawer_reopens_and_restores_grid_and_chart_focus(page: Page, live_server_url: str) -> None:
    ready(page, live_server_url)
    page.locator('[data-nav-value="explorer"]').first.click()
    table = page.locator("#explorer-table")
    expect(table).to_be_visible(timeout=20_000)
    row = table.locator("tbody tr").first
    row.click()
    drawer = page.locator('.city-detail-drawer[role="dialog"]')
    expect(drawer).to_be_visible(timeout=20_000)

    drawer.locator("[data-detail-close]").first.click()
    expect(drawer).to_be_hidden(timeout=20_000)
    table.locator("tbody tr").first.click()
    expect(drawer).to_be_visible(timeout=20_000)

    drawer.locator("[data-detail-close]").first.click()
    expect(drawer).to_be_hidden(timeout=20_000)
    table.locator("tbody tr").first.click()
    expect(drawer).to_be_visible(timeout=20_000)
    page.evaluate(
        """() => {
            const selected = document.querySelector('#explorer-table tbody tr');
            if (selected) selected.remove();
        }"""
    )
    drawer.locator("[data-detail-close]").first.click()
    expect(drawer).to_be_hidden(timeout=20_000)
    page.wait_for_function(
        "() => Boolean(document.activeElement && document.activeElement.closest('#explorer-table'))",
        timeout=20_000,
    )

    chart = page.locator("#explorer-chart .js-plotly-plot")
    expect(chart).to_be_visible(timeout=20_000)
    chart.locator("g.bars path").first.click(force=True)
    expect(drawer).to_be_visible(timeout=20_000)
    drawer.locator("[data-detail-close]").first.click()
    expect(drawer).to_be_hidden(timeout=20_000)
    page.wait_for_function(
        "() => Boolean(document.activeElement && document.activeElement.closest('#explorer-chart'))",
        timeout=20_000,
    )


def test_changed_row_reopens_after_close_and_browser_back_closes_drawer(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    page.locator('[data-nav-value="overview"]').first.click()
    page.locator('[data-nav-value="changed"]').first.click()
    expect(page.locator("#changed-table")).to_be_visible(timeout=20_000)
    row = page.locator("#changed-table tbody tr").first
    row.click()
    drawer = page.locator('.city-detail-drawer[role="dialog"]')
    expect(drawer).to_be_visible(timeout=20_000)

    drawer.locator("[data-detail-close]").first.click()
    expect(drawer).to_be_hidden(timeout=20_000)
    page.locator("#changed-table tbody tr").first.click()
    expect(drawer).to_be_visible(timeout=20_000)

    page.go_back()
    expect(page).to_have_url(re.compile(r"#overview$"), timeout=20_000)
    expect(drawer).to_be_hidden(timeout=20_000)
    expect(page.get_by_role("heading", name="Sacramento Budget Dashboard")).to_be_visible(timeout=20_000)


def test_bookmark_restored_open_drawer_closes_to_stable_focus_fallback(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    page.locator(".city-movement").first.click()
    drawer = page.locator('.city-detail-drawer[role="dialog"]')
    expect(drawer).to_be_visible(timeout=20_000)
    drawer.locator("[data-detail-copy]").first.click()
    expect(page).to_have_url(re.compile(r"_inputs_"), timeout=20_000)

    restored = page.context.new_page()
    restored.goto(page.url, wait_until="domcontentloaded")
    expect(restored.locator(".city-source-status--fresh")).to_be_visible(timeout=30_000)
    restored_drawer = restored.locator('.city-detail-drawer[role="dialog"]')
    expect(restored_drawer).to_be_visible(timeout=20_000)
    restored_drawer.locator("[data-detail-close]").first.click()
    expect(restored_drawer).to_be_hidden(timeout=20_000)
    assert restored.evaluate("document.activeElement && document.activeElement.id") in {
        "overview-analysis-workspace",
        "main",
    }
    restored.close()


def test_legacy_drilldown_maps_to_overview_workspace(page: Page, live_server_url: str) -> None:
    ready(page, f"{live_server_url}/#drilldown")
    expect(page).to_have_url(re.compile(r"#overview$"), timeout=20_000)
    workspace = page.locator("#overview-analysis-workspace")
    expect(workspace).to_be_visible(timeout=20_000)
    expect(workspace).to_be_focused(timeout=20_000)
    expect(page.get_by_role("heading", name="Explore the selected budget context")).to_be_visible()


def test_legacy_drilldown_query_maps_to_sanitized_overview_workspace(
    page: Page, live_server_url: str
) -> None:
    query = urlencode(
        {
            "_inputs_": "",
            "app_view": json.dumps("drilldown"),
            "drilldown-year": json.dumps("2027"),
            "drilldown-compare": json.dumps("2026"),
            "drilldown-flow": json.dumps("expense"),
            "drilldown-fund_scope": json.dumps("all_funds"),
            "drilldown-department": json.dumps("Police"),
            "drilldown-fund": json.dumps("General Fund"),
            "drilldown-category": json.dumps("Employee Services"),
        }
    )
    ready(page, f"{live_server_url}/?{query}")
    expect(page).to_have_url(re.compile(r"#overview$"), timeout=20_000)
    workspace = page.locator("#overview-analysis-workspace")
    expect(workspace).to_be_visible(timeout=20_000)
    expect(page.locator("#overview-workspace_department")).to_have_value("Police", timeout=20_000)
    expect(page.locator("#overview-workspace_fund")).to_have_value("General Fund", timeout=20_000)
    expect(page.locator("#overview-workspace_category")).to_have_value("Employee Services", timeout=20_000)


def test_mobile_menu_keyboard_skip_link_and_width(page: Page, live_server_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    ready(page, live_server_url)
    expect(page.locator(".city-nav")).to_be_hidden()
    assert_no_horizontal_overflow(page)
    page.locator(".city-mobile-nav__summary").click()
    expect(page.locator(".city-mobile-nav")).to_be_visible()
    page.locator('.city-mobile-nav__link[data-nav-value="methods"]').click()
    expect(page.get_by_role("heading", name="Sources & Methods")).to_be_visible()
    assert_no_horizontal_overflow(page)

    page.goto(live_server_url, wait_until="domcontentloaded")
    page.keyboard.press("Tab")
    expect(page.locator(".skip-link")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("main")).to_be_focused()


def test_mobile_detail_bottom_sheet_traps_focus_and_restores_escape(page: Page, live_server_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    ready(page, live_server_url)
    movement = page.locator(".city-movement").first
    movement.click()

    drawer = page.locator('.city-detail-drawer[role="dialog"]')
    expect(drawer).to_be_visible(timeout=20_000)
    box = drawer.bounding_box()
    viewport_height = page.evaluate("window.innerHeight")
    assert box is not None
    assert box["height"] < viewport_height

    close = drawer.locator("[data-detail-close]").first
    expect(close).to_be_focused()
    page.keyboard.down("Shift")
    page.keyboard.press("Tab")
    page.keyboard.up("Shift")
    assert page.evaluate(
        "Boolean(document.activeElement && document.activeElement.closest('.city-detail-drawer'))"
    )
    page.keyboard.press("Tab")
    expect(close).to_be_focused()

    page.keyboard.press("Escape")
    expect(drawer).to_be_hidden(timeout=20_000)
    expect(movement).to_be_focused(timeout=20_000)

    movement.click()
    expect(drawer).to_be_visible(timeout=20_000)
    drawer.locator("[data-detail-expand]").click()
    workspace = page.locator("#overview-analysis-workspace")
    expect(workspace).to_be_visible(timeout=20_000)
    assert_no_horizontal_overflow(page)
    workspace.locator(".city-movement").first.click()
    expect(drawer).to_be_visible(timeout=20_000)
    assert_no_horizontal_overflow(page)


def test_mobile_hierarchy_drawer_resets_scroll_and_keeps_header_visible(
    page: Page, live_server_url: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    ready(page, live_server_url)
    page.locator(".city-movement").first.click()

    drawer = page.locator('.city-detail-drawer[role="dialog"]')
    title = drawer.locator(".city-detail-drawer__title")
    expect(drawer).to_be_visible(timeout=20_000)
    previous_title = title.inner_text()

    drawer.locator("[data-detail-expand]").click()
    workspace = page.locator("#overview-analysis-workspace")
    expect(workspace).to_be_visible(timeout=20_000)
    workspace.locator(".city-movement").first.click()
    page.wait_for_function(
        """previous => {
          const title = document.querySelector('.city-detail-drawer__title');
          return title && title.textContent.trim() !== previous;
        }""",
        arg=previous_title,
        timeout=20_000,
    )
    previous_title = title.inner_text()

    drawer.locator("[data-detail-expand]").click()
    expect(workspace).to_be_visible(timeout=20_000)
    workspace.locator(".city-movement").first.click()
    page.wait_for_function(
        """previous => {
          const title = document.querySelector('.city-detail-drawer__title');
          return title && title.textContent.trim() !== previous;
        }""",
        arg=previous_title,
        timeout=20_000,
    )

    metrics = drawer.evaluate(
        """node => {
          const body = node.querySelector('.city-detail-drawer__body');
          const close = node.querySelector(
            '.city-detail-drawer__header [data-detail-close]'
          );
          const drawerRect = node.getBoundingClientRect();
          const closeRect = close.getBoundingClientRect();
          return {
            drawerScroll: node.scrollTop,
            bodyScroll: body.scrollTop,
            closeTop: closeRect.top,
            closeBottom: closeRect.bottom,
            drawerTop: drawerRect.top,
            drawerBottom: drawerRect.bottom
          };
        }"""
    )
    assert metrics["drawerScroll"] == 0
    assert metrics["bodyScroll"] == 0
    assert metrics["closeTop"] >= metrics["drawerTop"] - 1
    assert metrics["closeBottom"] <= metrics["drawerBottom"] + 1
    expect(drawer.locator(".city-detail-drawer__header [data-detail-close]")).to_be_focused()


def test_page_has_no_horizontal_overflow_at_common_viewports(page: Page, live_server_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    ready(page, live_server_url)
    for width in (390, 768, 1024, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        assert_no_horizontal_overflow(page)


def test_full_source_error_state(page: Page, error_server_url: str) -> None:
    page.goto(error_server_url, wait_until="domcontentloaded")
    expect(page.locator(".city-source-status--error")).to_contain_text(
        "No valid snapshot is cached",
        timeout=20_000,
    )
    expect(page.get_by_role("button", name="Retry source")).to_be_visible()
