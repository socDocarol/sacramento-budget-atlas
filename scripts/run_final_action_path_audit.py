"""Exercise final local-only drawer and Overview trigger paths on one trusted URL."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

SHELL = ".city-detail-overlay[data-detail-overlay]"
DRAWER = f"{SHELL} .city-detail-drawer"


def record_errors(page: Page, origin: str) -> list[str]:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on(
        "console",
        lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None,
    )
    page.on(
        "response",
        lambda response: errors.append(f"http:{response.status} {response.url}")
        if response.url.startswith(origin) and response.status >= 400
        else None,
    )
    return errors


def wait_rendered_chart(page: Page) -> None:
    page.wait_for_function(
        """() => {
          const widget = document.querySelector('#overview-trend_chart');
          const plot = widget && widget.querySelector('.js-plotly-plot');
          return Boolean(widget && !widget.classList.contains('recalculating') && plot &&
            plot.querySelector('.main-svg') &&
            plot.querySelector('.point, .slice, .box, .scatterlayer path, .barlayer path'));
        }""",
        timeout=35_000,
    )


def ready(page: Page, url: str) -> None:
    response = page.goto(f"{url.rstrip('/')}/#overview", wait_until="domcontentloaded")
    if response is None or not response.ok:
        status = response.status if response else "no response"
        raise RuntimeError(f"Overview navigation failed with status {status}")
    page.locator(".city-source-status--fresh").wait_for(state="visible", timeout=45_000)
    page.locator("[data-view-section='overview']").wait_for(state="visible", timeout=30_000)
    page.wait_for_function(
        """() => !document.querySelector("[data-view-section='overview'] .recalculating")""",
        timeout=30_000,
    )
    wait_rendered_chart(page)


def wait_open(page: Page) -> None:
    page.locator(DRAWER).wait_for(state="visible", timeout=25_000)
    page.wait_for_function(
        """() => {
          const shell = document.querySelector('.city-detail-overlay[data-detail-overlay]');
          const title = shell?.querySelector('.city-detail-drawer__title');
          return shell?.getAttribute('data-detail-lifecycle') === 'open' && Boolean(title?.textContent?.trim());
        }""",
        timeout=25_000,
    )


def closed_state(page: Page) -> dict[str, object]:
    page.wait_for_function(
        """() => {
          const shell = document.querySelector('.city-detail-overlay[data-detail-overlay]');
          const active = document.activeElement;
          return shell?.getAttribute('data-detail-lifecycle') === 'closed' &&
            Boolean(active && !active.closest('[data-detail-overlay]'));
        }""",
        timeout=4_000,
    )
    state = page.evaluate(
        """() => {
          const shell = document.querySelector('.city-detail-overlay[data-detail-overlay]');
          const active = document.activeElement;
          return {
            shellCount: document.querySelectorAll('.city-detail-overlay[data-detail-overlay]').length,
            lifecycle: shell?.getAttribute('data-detail-lifecycle') || null,
            ariaHidden: shell?.getAttribute('aria-hidden') || null,
            bodyOverflow: document.body.style.overflow,
            scrollLock: document.body.getAttribute('data-city-scroll-lock'),
            inertMarkedNodes: document.querySelectorAll('[data-city-inert-before]').length,
            activeId: active?.id || null,
            activeInDrawer: Boolean(active?.closest('[data-detail-overlay]')),
          };
        }"""
    )
    expected = {
        "shellCount": 1,
        "lifecycle": "closed",
        "ariaHidden": "true",
        "bodyOverflow": "",
        "scrollLock": None,
        "inertMarkedNodes": 0,
        "activeInDrawer": False,
    }
    if any(state[key] != value for key, value in expected.items()):
        raise RuntimeError(f"Closed cleanup mismatch: {state}")
    return state


def open_from_first_movement(page: Page) -> None:
    page.locator(".city-movement").first.click()
    wait_open(page)


def run_action(
    browser: object, url: str, name: str, action: Callable[[Page], dict[str, object]]
) -> dict[str, object]:
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = record_errors(page, url.rstrip("/"))
    try:
        ready(page, url)
        result = action(page)
        if errors:
            raise RuntimeError(f"Browser or local HTTP errors: {errors}")
        return {"name": name, "passed": True, "result": result, "errors": errors}
    except Exception as error:  # noqa: BLE001 - durable audit continues through every requested action
        return {"name": name, "passed": False, "error": str(error), "errors": errors}
    finally:
        page.close()


def footer_close(page: Page) -> dict[str, object]:
    open_from_first_movement(page)
    page.locator(f"{DRAWER} .city-detail-drawer__actions [data-detail-close]").click()
    return closed_state(page)


def header_close(page: Page) -> dict[str, object]:
    open_from_first_movement(page)
    page.locator(f"{DRAWER} .city-detail-drawer__header [data-detail-close]").click()
    return closed_state(page)


def backdrop_close(page: Page) -> dict[str, object]:
    open_from_first_movement(page)
    page.locator(f"{SHELL} [data-detail-backdrop]").click(force=True)
    return closed_state(page)


def clear_selection(page: Page) -> dict[str, object]:
    open_from_first_movement(page)
    page.locator(f"{DRAWER} [data-detail-clear]").click()
    state = closed_state(page)
    state["selectedMovements"] = page.locator(".city-movement.is-selected").count()
    return state


def inspect_records(page: Page) -> dict[str, object]:
    open_from_first_movement(page)
    page.locator(f"{DRAWER} [data-detail-inspect]").click()
    page.locator("#overview-records").wait_for(state="visible", timeout=25_000)
    state = closed_state(page)
    state["recordsVisible"] = page.locator("#overview-records").is_visible()
    state["recordsFocused"] = page.evaluate(
        """() => Boolean(document.activeElement && document.activeElement.closest('#overview-records'))"""
    )
    if not state["recordsVisible"] or not state["recordsFocused"]:
        raise RuntimeError(f"Inspect records focus mismatch: {state}")
    return state


def kpi_trigger(index: int) -> Callable[[Page], dict[str, object]]:
    def exercise(page: Page) -> dict[str, object]:
        kpis = page.locator(".city-kpi-button")
        count = kpis.count()
        if count != 4:
            raise RuntimeError(f"Expected four Overview KPI triggers, found {count}")
        label = kpis.nth(index).get_attribute("aria-label")
        kpis.nth(index).click()
        wait_open(page)
        page.locator(f"{DRAWER} .city-detail-drawer__header [data-detail-close]").click()
        state = closed_state(page)
        state["label"] = label
        return state

    return exercise


def trend_mark(page: Page) -> dict[str, object]:
    mark = page.locator(
        "#overview-trend_chart .point, #overview-trend_chart .barlayer path, "
        "#overview-trend_chart .scatterlayer path"
    ).first
    mark.wait_for(state="visible", timeout=25_000)
    mark.click(force=True)
    wait_open(page)
    page.locator(f"{DRAWER} .city-detail-drawer__header [data-detail-close]").click()
    return closed_state(page)


def cached_local_reload(page: Page, origin: str) -> dict[str, object]:
    response = page.reload(wait_until="domcontentloaded")
    if response is None or not response.ok:
        status = response.status if response else "no response"
        raise RuntimeError(f"Cached local reload failed with status {status}")
    page.locator(".city-source-status--fresh").wait_for(state="visible", timeout=45_000)
    wait_rendered_chart(page)
    return {
        "status": response.status,
        "localOnly": page.url.startswith(origin.rstrip("/")),
        "shellCount": page.locator(SHELL).count(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8002")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    actions: list[tuple[str, Callable[[Page], dict[str, object]]]] = [
        ("drawer_footer_close", footer_close),
        ("drawer_backdrop_click", backdrop_close),
        ("drawer_clear_selection", clear_selection),
        ("drawer_inspect_records", inspect_records),
        ("drawer_header_close", header_close),
        *((f"overview_kpi_{index + 1}", kpi_trigger(index)) for index in range(4)),
        ("overview_trend_chart_mark", trend_mark),
        ("cached_local_reload", lambda page: cached_local_reload(page, args.url)),
    ]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        results = [run_action(browser, args.url, name, action) for name, action in actions]
        browser.close()
    summary = {
        "target": args.url,
        "externalRefreshCalled": False,
        "results": results,
        "allPassed": all(result["passed"] for result in results),
    }
    path = output / "action-path-audit.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["allPassed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
