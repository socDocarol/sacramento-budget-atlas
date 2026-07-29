"""Capture final drawer evidence only after the authoritative browser suite is quiet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

SHELL = ".city-detail-overlay[data-detail-overlay]"
DRAWER = f"{SHELL} .city-detail-drawer"
DESKTOP_WIDTHS = (1024, 1440, 1920)
ZOOM_EQUIVALENT_WIDTHS = (("125", 1152), ("150", 960), ("200", 720))


def wait_rendered_charts(page: Page, root_selector: str, *, required: bool = True) -> None:
    page.wait_for_function(
        """args => {
          const root = document.querySelector(args.selector);
          if (!root) return false;
          const widgets = Array.from(root.querySelectorAll('.shiny-ipywidget-output')).filter(widget => {
            const style = window.getComputedStyle(widget);
            const rect = widget.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          });
          if (!widgets.length) return !args.required;
          return widgets.every(widget => {
            const plot = widget.querySelector('.js-plotly-plot');
            return !widget.classList.contains('recalculating') && plot && plot.querySelector('.main-svg') &&
              plot.querySelector('.point, .slice, .box, .scatterlayer path, .barlayer path');
          });
        }""",
        arg={"selector": root_selector, "required": required},
        timeout=35_000,
    )
    page.wait_for_timeout(500)


def wait_ready(page: Page, url: str, view: str = "overview") -> None:
    response = page.goto(f"{url.rstrip('/')}/#{view}", wait_until="domcontentloaded")
    if response is None or not response.ok:
        status = response.status if response else "no response"
        raise RuntimeError(f"Navigation to {view} failed with status {status}")
    page.locator(".city-source-status--fresh").wait_for(state="visible", timeout=45_000)
    section = f"[data-view-section='{view}']"
    page.locator(section).wait_for(state="visible", timeout=30_000)
    page.wait_for_function(
        """selector => !document.querySelector(selector + ' .recalculating')""",
        arg=section,
        timeout=30_000,
    )
    wait_rendered_charts(page, section)
    page.evaluate("window.scrollTo(0, 0)")


def wait_drawer(page: Page) -> None:
    page.locator(DRAWER).wait_for(state="visible", timeout=25_000)
    page.locator(SHELL).wait_for(state="visible", timeout=25_000)
    page.wait_for_function(
        """() => {
          const shell = document.querySelector('.city-detail-overlay[data-detail-overlay]');
          const drawer = shell && shell.querySelector('.city-detail-drawer');
          const title = drawer && drawer.querySelector('.city-detail-drawer__title');
          const total = drawer && drawer.querySelector('.city-detail-metrics .city-stat-card__value');
          const amount = drawer && drawer.querySelector('.city-detail-change__amount');
          const percent = drawer && drawer.querySelector('.city-detail-change__percent');
          return shell?.getAttribute('data-detail-lifecycle') === 'open' && Boolean(
            title?.textContent?.trim() && total?.textContent?.trim() &&
            amount?.textContent?.trim() && percent?.textContent?.trim()
          );
        }""",
        timeout=35_000,
    )
    wait_rendered_charts(page, DRAWER)


def wait_drawer_closed(page: Page) -> None:
    page.wait_for_function(
        """() => document.querySelector('.city-detail-overlay[data-detail-overlay]')
          ?.getAttribute('data-detail-lifecycle') === 'closed'""",
        timeout=25_000,
    )


def geometry(page: Page) -> dict[str, object]:
    return page.evaluate(
        """() => {
          const drawer = document.querySelector('.city-detail-overlay[data-detail-overlay] .city-detail-drawer');
          const metrics = Array.from(document.querySelectorAll(
            '.city-detail-change, .city-detail-metric, .city-detail-change__amount, .city-detail-change__percent'
          )).map(node => ({ scrollWidth: node.scrollWidth, clientWidth: node.clientWidth }));
          const rect = drawer && drawer.getBoundingClientRect();
          return {
            rootOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            bodyOverflow: document.body.scrollWidth - document.body.clientWidth,
            drawer: rect ? { left: rect.left, right: rect.right, width: rect.width, height: rect.height } : null,
            metricOverflow: metrics.filter(metric => metric.scrollWidth > metric.clientWidth).length,
            drawablePlots: document.querySelectorAll('.js-plotly-plot .main-svg').length
          };
        }"""
    )


def screenshot(page: Page, output: Path, name: str, errors: list[str]) -> dict[str, object]:
    metrics = geometry(page)
    if errors:
        raise RuntimeError(f"{name} produced browser errors: {'; '.join(errors)}")
    if metrics["rootOverflow"] != 0 or metrics["bodyOverflow"] != 0:
        raise RuntimeError(f"{name} has horizontal overflow: {metrics}")
    path = output / f"{name}.png"
    page.screenshot(path=path, animations="disabled")
    return {"name": name, "path": str(path), "metrics": metrics}


def new_page(browser: object, width: int, height: int) -> tuple[Page, list[str]]:
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on(
        "console",
        lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None,
    )
    return page, errors


def capture_department(browser: object, url: str, output: Path, width: int) -> dict[str, object]:
    page, errors = new_page(browser, width, 1080 if width >= 1440 else 900)
    try:
        wait_ready(page, url)
        page.locator(".city-movement").first.click()
        wait_drawer(page)
        return screenshot(page, output, f"department-open-{width}", errors)
    finally:
        page.close()


def capture_hierarchy(browser: object, url: str, output: Path) -> list[dict[str, object]]:
    page, errors = new_page(browser, 1440, 1000)
    captures: list[dict[str, object]] = []
    try:
        wait_ready(page, url)
        page.locator(".city-movement").first.click()
        wait_drawer(page)
        department_title = page.locator(f"{DRAWER} .city-detail-drawer__title").inner_text()
        page.locator(f"{DRAWER} [data-detail-expand]").click()
        workspace = page.locator("#overview-analysis-workspace")
        workspace.wait_for(state="visible", timeout=25_000)
        wait_drawer_closed(page)
        wait_rendered_charts(page, "[data-view-section='overview']")
        captures.append(screenshot(page, output, "expanded-workspace-1440", errors))

        workspace.locator(".city-movement").first.click()
        page.wait_for_function(
            """() => document.querySelector('.city-detail-overlay[data-detail-overlay]')
              ?.getAttribute('data-detail-lifecycle') === 'open'""",
            timeout=25_000,
        )
        page.wait_for_function(
            """previous => {
              const title = document.querySelector('.city-detail-drawer__title');
              return title && title.textContent.trim() && title.textContent.trim() !== previous;
            }""",
            arg=department_title,
            timeout=25_000,
        )
        wait_drawer(page)
        captures.append(screenshot(page, output, "fund-open-1440", errors))

        fund_title = page.locator(f"{DRAWER} .city-detail-drawer__title").inner_text()
        page.locator(f"{DRAWER} [data-detail-expand]").click()
        workspace.wait_for(state="visible", timeout=25_000)
        wait_drawer_closed(page)
        wait_rendered_charts(page, "[data-view-section='overview']")
        workspace.locator(".city-movement").first.click()
        page.wait_for_function(
            """() => document.querySelector('.city-detail-overlay[data-detail-overlay]')
              ?.getAttribute('data-detail-lifecycle') === 'open'""",
            timeout=25_000,
        )
        page.wait_for_function(
            """previous => {
              const title = document.querySelector('.city-detail-drawer__title');
              return title && title.textContent.trim() && title.textContent.trim() !== previous;
            }""",
            arg=fund_title,
            timeout=25_000,
        )
        wait_drawer(page)
        captures.append(screenshot(page, output, "category-open-1440", errors))
    finally:
        page.close()
    return captures


def capture_exact_record(browser: object, url: str, output: Path) -> dict[str, object]:
    page, errors = new_page(browser, 1440, 1000)
    try:
        wait_ready(page, url, "explorer")
        row = page.locator("#explorer-table tbody tr").first
        row.wait_for(state="visible", timeout=30_000)
        row.click()
        wait_drawer(page)
        return screenshot(page, output, "exact-record-open-1440", errors)
    finally:
        page.close()


def capture_longest(browser: object, url: str, output: Path) -> dict[str, object]:
    page, errors = new_page(browser, 1440, 1000)
    try:
        wait_ready(page, url)
        index = page.locator(".city-movement").evaluate_all(
            """nodes => nodes.reduce((longest, node, index) =>
              node.textContent.trim().length > nodes[longest].textContent.trim().length ? index : longest, 0)"""
        )
        page.locator(".city-movement").nth(index).click()
        wait_drawer(page)
        return screenshot(page, output, "longest-metric-breadcrumb-1440", errors)
    finally:
        page.close()


def capture_zoom_equivalents(browser: object, url: str, output: Path) -> list[dict[str, object]]:
    captures: list[dict[str, object]] = []
    for label, width in ZOOM_EQUIVALENT_WIDTHS:
        page, errors = new_page(browser, width, 1080)
        try:
            wait_ready(page, url)
            page.locator(".city-movement").first.click()
            wait_drawer(page)
            captures.append(screenshot(page, output, f"zoom-equivalent-{label}-effective-{width}", errors))
        finally:
            page.close()
    return captures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    captures: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width in DESKTOP_WIDTHS:
            captures.append(capture_department(browser, args.url, output, width))

        page, errors = new_page(browser, 390, 844)
        try:
            wait_ready(page, args.url)
            page.locator(".city-movement").first.click()
            wait_drawer(page)
            captures.append(screenshot(page, output, "mobile-bottom-sheet-390", errors))
        finally:
            page.close()

        captures.extend(capture_hierarchy(browser, args.url, output))
        captures.append(capture_exact_record(browser, args.url, output))
        captures.append(capture_longest(browser, args.url, output))
        captures.extend(capture_zoom_equivalents(browser, args.url, output))
        browser.close()

    summary = {"target": args.url, "captures": captures}
    summary_path = output / "capture-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(captures)} final drawer captures to {output}")


if __name__ == "__main__":
    main()
