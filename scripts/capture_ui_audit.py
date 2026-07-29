"""Capture stable UX audit screenshots for every supported viewport and view."""

from __future__ import annotations

import argparse
from contextlib import suppress
from pathlib import Path

from playwright.sync_api import Page, TimeoutError, sync_playwright

VIEWPORTS = {
    390: 844,
    768: 960,
    1024: 900,
    1440: 1000,
    1920: 1080,
}
VIEWS = ("overview", "changed", "explorer", "lab", "budget101", "methods")


def _watch_browser_errors(page: Page) -> list[str]:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on(
        "console",
        lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None,
    )
    return errors


def _assert_page_contract(page: Page, label: str, browser_errors: list[str]) -> None:
    contract = page.evaluate(
        """() => {
          const authoredNodes = Array.from(document.querySelectorAll('[id]')).filter(
            node => !node.closest('.js-plotly-plot')
          );
          const ids = authoredNodes.map(node => node.id);
          const duplicates = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
          const hasScrollableAncestor = node => {
            let parent = node.parentElement;
            while (parent && parent !== document.body) {
              const style = window.getComputedStyle(parent);
              if (['auto', 'scroll'].includes(style.overflowX) &&
                  parent.scrollWidth > parent.clientWidth) return true;
              parent = parent.parentElement;
            }
            return false;
          };
          const isVisible = node => {
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              rect.width > 0 && rect.height > 0;
          };
          const isPerceivable = node => isVisible(node) &&
            !node.closest('[inert], [aria-hidden="true"]');
          const labelledByText = node => (node.getAttribute('aria-labelledby') || '')
            .split(/\\s+/)
            .filter(Boolean)
            .map(id => document.getElementById(id))
            .filter(Boolean)
            .map(label => label.textContent.trim())
            .join(' ');
          const associatedLabel = node => {
            const wrappingLabel = node.closest('label');
            if (wrappingLabel) return wrappingLabel.textContent.trim();
            if (node.id) {
              const escaped = window.CSS && CSS.escape ? CSS.escape(node.id) : node.id;
              const label = document.querySelector(`label[for="${escaped}"]`);
              if (label) return label.textContent.trim();
            }
            return '';
          };
          const explicitName = node => [
            node.getAttribute('aria-label'),
            labelledByText(node),
            associatedLabel(node),
            node.getAttribute('alt'),
            node.getAttribute('title')
          ].find(value => value && value.trim()) || '';
          const accessibleName = node => {
            const explicit = explicitName(node);
            if (explicit) return explicit;
            if (node.matches('input, select, textarea')) return '';
            return node.textContent.trim();
          };
          const clippedControls = Array.from(
            document.querySelectorAll('a[href], button, input, select, summary')
          ).filter(node => {
            const rect = node.getBoundingClientRect();
            const clipped = rect.left < -1 || rect.right > window.innerWidth + 1;
            return isPerceivable(node) && clipped && !hasScrollableAncestor(node);
          }).map(node => node.id || node.textContent.trim().slice(0, 60));
          const unnamedControls = Array.from(
            document.querySelectorAll(
              'a[href], button, input:not([type="hidden"]), select, textarea, summary'
            )
          ).filter(node => isPerceivable(node) && !node.closest('.js-plotly-plot') &&
              !accessibleName(node))
            .map(node => node.id || node.tagName.toLowerCase());
          const unlabelledImages = Array.from(document.querySelectorAll('img'))
            .filter(node => isPerceivable(node) && !node.hasAttribute('alt'))
            .map(node => node.id || node.getAttribute('src') || 'img');
          const dialogIssues = Array.from(document.querySelectorAll('[role="dialog"]'))
            .filter(isPerceivable)
            .filter(node => node.getAttribute('aria-modal') !== 'true' ||
              !(node.getAttribute('aria-label') || labelledByText(node)))
            .map(node => node.id || 'dialog');
          const dialogHeaderIssues = Array.from(document.querySelectorAll('[role="dialog"]'))
            .filter(isPerceivable)
            .filter(node => {
              const close = node.querySelector(
                '.city-detail-drawer__header [data-detail-close]'
              );
              if (!close) return true;
              const dialogRect = node.getBoundingClientRect();
              const closeRect = close.getBoundingClientRect();
              return closeRect.top < dialogRect.top - 1 ||
                closeRect.bottom > dialogRect.bottom + 1;
            })
            .map(node => node.id || 'dialog');
          const visibleHeadings = Array.from(document.querySelectorAll('h1')).filter(isVisible);
          return {
            mains: document.querySelectorAll('main').length,
            visibleH1s: visibleHeadings.length,
            overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            duplicates,
            clippedControls,
            unnamedControls,
            unlabelledImages,
            dialogIssues,
            dialogHeaderIssues
          };
        }"""
    )
    problems = list(browser_errors)
    if contract["mains"] != 1:
        problems.append(f"expected one main landmark, found {contract['mains']}")
    if contract["visibleH1s"] != 1:
        problems.append(f"expected one visible h1, found {contract['visibleH1s']}")
    if contract["overflow"] > 0:
        problems.append(f"page-level horizontal overflow: {contract['overflow']} pixels")
    if contract["duplicates"]:
        problems.append(f"duplicate IDs: {', '.join(contract['duplicates'])}")
    if contract["clippedControls"]:
        problems.append(f"clipped controls: {', '.join(contract['clippedControls'])}")
    if contract["unnamedControls"]:
        problems.append(f"unnamed controls: {', '.join(contract['unnamedControls'])}")
    if contract["unlabelledImages"]:
        problems.append(f"images without alt text: {', '.join(contract['unlabelledImages'])}")
    if contract["dialogIssues"]:
        problems.append(f"dialog accessibility issues: {', '.join(contract['dialogIssues'])}")
    if contract["dialogHeaderIssues"]:
        problems.append(
            f"dialog header controls outside the visible drawer: {', '.join(contract['dialogHeaderIssues'])}"
        )
    if problems:
        raise RuntimeError(f"{label} failed the capture contract: {'; '.join(problems)}")


def _assert_explorer_chart_geometry(page: Page, width: int) -> None:
    metrics = page.evaluate(
        """() => {
          const plot = document.querySelector('#explorer-chart .js-plotly-plot');
          if (!plot) return null;
          const plotRect = plot.getBoundingClientRect();
          const tickRects = Array.from(plot.querySelectorAll('.yaxislayer-above .ytick text'))
            .map(node => node.getBoundingClientRect());
          const barRects = Array.from(plot.querySelectorAll('.barlayer path'))
            .map(node => node.getBoundingClientRect());
          return {
            plotWidth: plotRect.width,
            widestTick: Math.max(0, ...tickRects.map(rect => rect.width)),
            widestBar: Math.max(0, ...barRects.map(rect => rect.width)),
            internalLegends: Array.from(plot.querySelectorAll('.legend'))
              .filter(node => {
                const rect = node.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
              }).length,
            externalKeyVisible: Boolean(
              document.querySelector('#explorer-chart_key .city-chart-key')
            )
          };
        }"""
    )
    if metrics is None:
        raise RuntimeError(f"Explorer at {width}px has no rendered comparison chart")
    problems: list[str] = []
    if metrics["internalLegends"]:
        problems.append("the Plotly legend overlaps the chart")
    if not metrics["externalKeyVisible"]:
        problems.append("the accessible external year key is missing")
    if width == 390:
        if metrics["widestTick"] > metrics["plotWidth"] * 0.46:
            problems.append("department axis labels dominate the mobile plot")
        if metrics["widestBar"] < metrics["plotWidth"] * 0.28:
            problems.append("the longest mobile bar has insufficient plot width")
    if problems:
        raise RuntimeError(f"Explorer at {width}px failed chart geometry: {'; '.join(problems)}")


def _wait_for_snapshot(page: Page) -> None:
    page.locator(".city-source-status").first.wait_for(timeout=45_000)


def _wait_for_rendered_charts(page: Page, root_selector: str) -> None:
    with suppress(TimeoutError):
        page.wait_for_function(
            """selector => {
              const root = document.querySelector(selector);
              if (!root) return false;
              const widgets = Array.from(
                root.querySelectorAll('.shiny-ipywidget-output, .city-client-plot')
              ).filter(
                widget => {
                  const style = window.getComputedStyle(widget);
                  const rect = widget.getBoundingClientRect();
                  return style.display !== 'none' && style.visibility !== 'hidden' &&
                    rect.width > 0 && rect.height > 0;
                }
              );
              return widgets.every(widget => {
                const plot = widget.classList.contains('js-plotly-plot')
                  ? widget
                  : widget.querySelector('.js-plotly-plot');
                return !widget.classList.contains('recalculating') &&
                  plot && plot.querySelector('.main-svg') &&
                  plot.querySelector('.point, .slice, .box, .scatterlayer path, .barlayer path');
              });
            }""",
            arg=root_selector,
            timeout=30_000,
        )
    page.wait_for_timeout(800)


def _wait_for_detail_title_change(page: Page, previous: str) -> None:
    page.wait_for_function(
        """previous => {
          const title = document.querySelector('.city-detail-drawer__title');
          return title && title.textContent.trim() && title.textContent.trim() !== previous;
        }""",
        arg=previous,
        timeout=20_000,
    )


def _wait_for_view(page: Page, view: str) -> None:
    selector = f"[data-view-section='{view}']"
    page.locator(selector).wait_for(state="visible", timeout=30_000)
    with suppress(TimeoutError):
        page.wait_for_function(
            """view => {
              const section = document.querySelector(`[data-view-section='${view}']`);
              return section && section.querySelectorAll('.recalculating').length === 0;
            }""",
            arg=view,
            timeout=20_000,
        )
    _wait_for_rendered_charts(page, selector)
    page.wait_for_timeout(800)


def _open_page(page: Page, base_url: str, view: str) -> None:
    page.goto(f"{base_url.rstrip('/')}/#{view}", wait_until="domcontentloaded")
    _wait_for_snapshot(page)
    _wait_for_view(page, view)
    page.evaluate("window.scrollTo(0, 0)")


def _capture_views(browser: object, base_url: str, output: Path) -> None:
    for width, height in VIEWPORTS.items():
        for view in VIEWS:
            page = browser.new_page(viewport={"width": width, "height": height})
            browser_errors = _watch_browser_errors(page)
            _open_page(page, base_url, view)
            _assert_page_contract(page, f"{view} at {width}px", browser_errors)
            if view == "explorer":
                _assert_explorer_chart_geometry(page, width)
            page.screenshot(
                path=output / f"{view}-{width}.png",
                full_page=True,
                animations="disabled",
            )
            page.close()


def _capture_detail_states(browser: object, base_url: str, output: Path) -> None:
    for width, height in VIEWPORTS.items():
        page = browser.new_page(viewport={"width": width, "height": height})
        browser_errors = _watch_browser_errors(page)
        _open_page(page, base_url, "overview")
        movement = page.locator(".city-movement").first
        movement.wait_for(state="visible", timeout=30_000)
        movement.click()
        page.get_by_role("dialog").wait_for(state="visible", timeout=20_000)
        _wait_for_rendered_charts(page, ".city-detail-drawer")
        _assert_page_contract(page, f"department detail at {width}px", browser_errors)
        page.screenshot(
            path=output / f"overview-department-{width}.png",
            animations="disabled",
        )

        department_title = page.locator(".city-detail-drawer__title").inner_text()
        page.get_by_role("button", name="Expand analysis").click()
        workspace = page.locator("#overview-analysis-workspace")
        workspace.wait_for(state="visible", timeout=30_000)
        _wait_for_rendered_charts(page, "[data-view-section='overview']")
        workspace.locator(".city-movement").first.click()
        page.get_by_role("dialog").wait_for(state="visible", timeout=20_000)
        _wait_for_detail_title_change(page, department_title)
        _wait_for_rendered_charts(page, ".city-detail-drawer")
        _assert_page_contract(page, f"fund detail at {width}px", browser_errors)
        page.screenshot(
            path=output / f"overview-fund-{width}.png",
            animations="disabled",
        )

        fund_title = page.locator(".city-detail-drawer__title").inner_text()
        page.get_by_role("button", name="Expand analysis").click()
        workspace.wait_for(state="visible", timeout=30_000)
        _wait_for_rendered_charts(page, "[data-view-section='overview']")
        workspace.locator(".city-movement").first.click()
        page.get_by_role("dialog").wait_for(state="visible", timeout=20_000)
        _wait_for_detail_title_change(page, fund_title)
        _wait_for_rendered_charts(page, ".city-detail-drawer")
        _assert_page_contract(page, f"category detail at {width}px", browser_errors)
        page.screenshot(
            path=output / f"overview-category-{width}.png",
            animations="disabled",
        )
        page.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("artifacts/ui-audit/after"))
    parser.add_argument(
        "--phase",
        choices=("all", "views", "details"),
        default="all",
        help="Capture all evidence, page views only, or hierarchy detail states only.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        if args.phase in {"all", "views"}:
            _capture_views(browser, args.url, args.output)
        if args.phase in {"all", "details"}:
            _capture_detail_states(browser, args.url, args.output)
        browser.close()

    print(f"Captured {len(list(args.output.glob('*.png')))} screenshots in {args.output}.")


if __name__ == "__main__":
    main()
