"""Capture a focused, additive runtime audit of the integrated drilldown drawer."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Page, TimeoutError, sync_playwright

VIEWPORTS = {
    390: 844,
    768: 960,
    1024: 900,
    1440: 1000,
    1920: 1080,
}
SHELL = ".city-detail-overlay[data-detail-overlay]"
DRAWER = f"{SHELL} .city-detail-drawer"
BRIEF_TIMING_BUDGETS_MS = {
    "shellFeedback": 300,
    "stableVisual": 300,
    "warmSummary": 1_200,
    "chartReady": None,
    "closeVisual": 300,
    "cleanup": 500,
}


def safe_path(url: str) -> str:
    """Keep artifact output free of bookmark query-string values."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def install_runtime_observers(page: Page) -> None:
    """Delay all probes until the overview root and persistent drawer shell exist."""
    del page


def wait_ready(page: Page, url: str) -> None:
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


def begin_runtime_measurement(page: Page, mark_name: str) -> None:
    """Attach observers after Shiny has replaced its initial document contents."""
    page.evaluate(
        """markName => {
          if (window.__drilldownAuditObserver) window.__drilldownAuditObserver.disconnect();
          const audit = window.__drilldownAudit = {
            longTasks: [], mutationCount: 0, mutationTargets: []
          };
          const root = document.querySelector("[data-view-section='overview']") || document.getElementById('main');
          if (!root) throw new Error('Overview root is not available for runtime measurement');
          const observer = new MutationObserver(records => {
            audit.mutationCount += records.length;
            for (const record of records) {
              if (audit.mutationTargets.length >= 20) break;
              const target = record.target;
              audit.mutationTargets.push(
                target.id || target.getAttribute?.('class') || target.nodeName.toLowerCase()
              );
            }
          });
          observer.observe(root, {
            childList: true,
            subtree: true,
            attributes: true,
            characterData: true
          });
          window.__drilldownAuditObserver = observer;
          if (window.PerformanceObserver) {
            try {
              new PerformanceObserver(list => {
                for (const entry of list.getEntries()) {
                  audit.longTasks.push({
                    startTime: Number(entry.startTime.toFixed(2)),
                    duration: Number(entry.duration.toFixed(2))
                  });
                }
              }).observe({ type: 'longtask', buffered: true });
            } catch (_) {}
          }
          performance.mark(markName);
        }""",
        arg=mark_name,
    )


def mark(page: Page, name: str) -> None:
    page.evaluate("name => performance.mark(name)", arg=name)


def page_contract(page: Page) -> dict[str, object]:
    return page.evaluate(
        """() => {
          const visible = node => {
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              rect.width > 0 && rect.height > 0;
          };
          const active = document.activeElement;
          return {
            overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            visibleH1s: Array.from(document.querySelectorAll('h1')).filter(visible).length,
            mains: document.querySelectorAll('main').length,
            dialogs: Array.from(document.querySelectorAll('[role="dialog"]')).filter(visible).length,
            focus: active ? (active.id || active.className || active.tagName.toLowerCase()) : null,
            bodyOverflow: document.body.style.overflow,
            scrollLock: document.body.getAttribute('data-city-scroll-lock'),
            inertMarkedNodes: document.querySelectorAll('[data-city-inert-before]').length
          };
        }"""
    )


def overlay_state(page: Page) -> dict[str, object]:
    return page.evaluate(
        """() => {
          const overlays = Array.from(document.querySelectorAll('.city-detail-overlay[data-detail-overlay]'));
          const shell = overlays[0] || null;
          const ids = window.__drilldownAuditOverlayIds || (window.__drilldownAuditOverlayIds = new WeakMap());
          const next = window.__drilldownAuditOverlayNext || 1;
          if (shell && !ids.has(shell)) {
            ids.set(shell, next);
            window.__drilldownAuditOverlayNext = next + 1;
          }
          const drawer = shell && shell.querySelector('.city-detail-drawer');
          const title = shell && shell.querySelector('.city-detail-drawer__title');
          return {
            activeOverlayId: shell ? ids.get(shell) : null,
            renderedOverlayCount: overlays.length,
            lifecycle: shell ? shell.getAttribute('data-detail-lifecycle') : null,
            ariaHidden: shell ? shell.getAttribute('aria-hidden') : null,
            title: title ? title.textContent.trim() : null,
            ariaModal: drawer ? drawer.getAttribute('aria-modal') : null,
            drawerRole: drawer ? drawer.getAttribute('role') : null,
            drawerTabIndex: drawer ? drawer.getAttribute('tabindex') : null,
            bodyOverflow: document.body.style.overflow,
            scrollLock: document.body.getAttribute('data-city-scroll-lock'),
            inertMarkedNodes: document.querySelectorAll('[data-city-inert-before]').length
          };
        }"""
    )


def runtime_metrics(page: Page) -> dict[str, object]:
    return page.evaluate(
        """() => {
          const audit = window.__drilldownAudit || { longTasks: [], mutationCount: 0, mutationTargets: [] };
          const navigation = performance.getEntriesByType('navigation')[0];
          return {
            navigation: navigation ? {
              domContentLoaded: Number(navigation.domContentLoadedEventEnd.toFixed(2)),
              loadEventEnd: Number(navigation.loadEventEnd.toFixed(2)),
              responseStart: Number(navigation.responseStart.toFixed(2)),
              duration: Number(navigation.duration.toFixed(2))
            } : null,
            longTaskCount: audit.longTasks.length,
            longestLongTaskMs: Math.max(0, ...audit.longTasks.map(entry => entry.duration)),
            longTasks: audit.longTasks,
            mutationCount: audit.mutationCount,
            mutationTargets: audit.mutationTargets,
            marks: performance.getEntriesByType('mark')
              .filter(entry => entry.name.startsWith('drilldown:'))
              .map(entry => ({ name: entry.name, startTime: Number(entry.startTime.toFixed(2)) }))
          };
        }"""
    )


def wait_lifecycle(page: Page, value: str, timeout: int = 10_000) -> None:
    page.wait_for_function(
        """expected => {
          const shell = document.querySelector('.city-detail-overlay[data-detail-overlay]');
          return shell && shell.getAttribute('data-detail-lifecycle') === expected;
        }""",
        arg=value,
        timeout=timeout,
    )


def install_lifecycle_probe(page: Page) -> None:
    """Measure only the persistent shell, never the document body or its full subtree."""
    page.evaluate(
        """() => {
          const shell = document.querySelector('.city-detail-overlay[data-detail-overlay]');
          const drawer = shell && shell.querySelector('.city-detail-drawer');
          if (!shell || !drawer) throw new Error('Persistent detail shell is unavailable');
          const now = () => Number(performance.now().toFixed(2));
          const dynamicValues = () => {
            const title = drawer.querySelector('.city-detail-drawer__title');
            const breadcrumb = drawer.querySelector('.city-breadcrumbs');
            const currentTotal = drawer.querySelector('.city-detail-metrics .city-stat-card__value');
            return {
              title: title ? title.textContent.trim() : '',
              breadcrumb: breadcrumb ? breadcrumb.textContent.trim() : '',
              currentTotal: currentTotal ? currentTotal.textContent.trim() : ''
            };
          };
          const chartContext = () => {
            const chart = drawer.querySelector('.js-plotly-plot');
            const status = drawer.querySelector('.city-detail-trend__status');
            return {
              mainSvgCount: chart ? chart.querySelectorAll('.main-svg').length : 0,
              drawableCount: chart ? chart.querySelectorAll(
                '.scatterlayer path, .barlayer path, .point, .slice'
              ).length : 0,
              signature: chart ? `${chart.innerHTML.length}|${chart.textContent.trim()}` : '',
              status: status ? status.textContent.trim() : '',
              loading: Boolean(drawer.querySelector('.city-detail-trend__status--loading'))
            };
          };
          const probe = {
            startedAt: now(), lifecycle: [], opacitySamples: [], shellCountAtStart:
              document.querySelectorAll('.city-detail-overlay[data-detail-overlay]').length,
            baselineDynamicValues: dynamicValues(),
            baselineChartContext: chartContext(),
            firstOpeningAt: null, ariaVisibleAt: null, backdropVisibleAt: null,
            stableVisualAt: null, warmSummaryAt: null, firstMetricAt: null, chartReadyAt: null,
            closeRequestedAt: null, firstClosingAt: null, closeVisualAt: null, closedAt: null,
            cleanupAt: null, lastVisual: null, stableFrames: 0
          };
          const captureLifecycle = () => {
            const lifecycle = shell.getAttribute('data-detail-lifecycle');
            const ariaHidden = shell.getAttribute('aria-hidden');
            probe.lifecycle.push({ at: now(), lifecycle, ariaHidden });
            if (lifecycle === 'opening' && probe.firstOpeningAt === null) {
              probe.firstOpeningAt = now();
              probe.closedAt = null;
              probe.cleanupAt = null;
            }
            if (ariaHidden === 'false' && probe.ariaVisibleAt === null) probe.ariaVisibleAt = now();
            if (lifecycle === 'closing' && probe.firstClosingAt === null) probe.firstClosingAt = now();
            if (lifecycle === 'closed' && probe.closeRequestedAt !== null && probe.closedAt === null) {
              probe.closedAt = now();
            }
          };
          const observer = new MutationObserver(captureLifecycle);
          observer.observe(shell, {
            attributes: true,
            attributeFilter: ['data-detail-lifecycle', 'aria-hidden', 'class', 'style']
          });
          const trigger = document.querySelector('.city-movement');
          if (trigger) trigger.addEventListener('pointerdown', () => {
            if (probe.activationAt === undefined) probe.activationAt = now();
          }, { capture: true, once: true });
          const sample = () => {
            const drawerStyle = window.getComputedStyle(drawer);
            const backdrop = shell.querySelector('[data-detail-backdrop]') || shell;
            const backdropStyle = window.getComputedStyle(backdrop);
            const drawerOpacity = Number(drawerStyle.opacity);
            const backdropOpacity = Number(backdropStyle.opacity);
            const transform = drawerStyle.transform;
            const at = now();
            const lifecycle = shell.getAttribute('data-detail-lifecycle');
            probe.opacitySamples.push({ at, lifecycle, drawerOpacity, backdropOpacity, transform });
            if ((lifecycle === 'opening' || lifecycle === 'open') && backdropOpacity > 0 &&
                probe.backdropVisibleAt === null) probe.backdropVisibleAt = at;
            const visual = `${drawerOpacity}|${backdropOpacity}|${transform}`;
            if (lifecycle === 'open') {
              probe.stableFrames = visual === probe.lastVisual ? probe.stableFrames + 1 : 0;
              if (probe.stableFrames >= 2 && probe.stableVisualAt === null) probe.stableVisualAt = at;
            }
            probe.lastVisual = visual;
            if (lifecycle === 'opening' || lifecycle === 'open') {
              const values = dynamicValues();
              const baseline = probe.baselineDynamicValues;
              const dynamicSummaryReady = values.title && values.breadcrumb && values.currentTotal &&
                (values.title !== baseline.title || values.breadcrumb !== baseline.breadcrumb ||
                  values.currentTotal !== baseline.currentTotal);
              if (dynamicSummaryReady && probe.warmSummaryAt === null) probe.warmSummaryAt = at;
              const metric = Array.from(drawer.querySelectorAll(
                '.city-detail-change__amount, .city-detail-change__percent'
              )).find(node => node.textContent.trim());
              if (metric && probe.firstMetricAt === null) probe.firstMetricAt = at;
              const chart = chartContext();
              const baselineChart = probe.baselineChartContext;
              const chartChanged = chart.mainSvgCount !== baselineChart.mainSvgCount ||
                chart.drawableCount !== baselineChart.drawableCount || chart.signature !== baselineChart.signature ||
                chart.status !== baselineChart.status;
              const chartRenderable = chart.mainSvgCount > 0 && chart.drawableCount > 0;
              if (probe.firstMetricAt !== null && chartChanged && chartRenderable && !chart.loading &&
                  probe.chartReadyAt === null) {
                probe.chartReadyAt = at;
              }
            }
            if (probe.closeRequestedAt !== null && probe.closeVisualAt === null) {
              const opening = probe.opacitySamples.find(entry => entry.lifecycle === 'open');
              if (opening && (drawerOpacity < opening.drawerOpacity - 0.01 ||
                  backdropOpacity < opening.backdropOpacity - 0.01 || transform !== opening.transform)) {
                probe.closeVisualAt = at;
              }
            }
            if (probe.closeRequestedAt !== null && lifecycle === 'closed' && probe.cleanupAt === null &&
                !document.body.style.overflow &&
                !document.body.hasAttribute('data-city-scroll-lock') &&
                !document.querySelector('[data-city-inert-before]')) {
              probe.cleanupAt = at;
            }
            if (probe.opacitySamples.length < 360) requestAnimationFrame(sample);
          };
          captureLifecycle();
          requestAnimationFrame(sample);
          window.__drilldownLifecycleProbe = probe;
          window.__drilldownLifecycleShell = shell;
          window.__drilldownLifecycleObserver = observer;
        }"""
    )


def lifecycle_probe_report(page: Page) -> dict[str, object]:
    return page.evaluate(
        """() => {
          const probe = window.__drilldownLifecycleProbe;
          const shell = document.querySelector('.city-detail-overlay[data-detail-overlay]');
          if (!probe || !shell) return null;
          const samples = probe.opacitySamples;
          const closeEnd = probe.closedAt ?? probe.cleanupAt ?? Infinity;
          const closing = samples.filter(sample =>
            probe.closeRequestedAt !== null && sample.at >= probe.closeRequestedAt && sample.at <= closeEnd
          );
          const opacityNonincreasing = closing.every((sample, index) => index === 0 ||
            sample.drawerOpacity <= closing[index - 1].drawerOpacity + 0.02);
          return {
            ...probe,
            shellIdentityRetained: shell === window.__drilldownLifecycleShell,
            shellCountAtEnd: document.querySelectorAll('.city-detail-overlay[data-detail-overlay]').length,
            opacityNonincreasing,
            closingOpacitySamples: closing
          };
        }"""
    )


def assess_lifecycle_timings(probe: dict[str, object]) -> dict[str, dict[str, object]]:
    started = probe.get("activationAt") or probe.get("startedAt")
    closed = probe.get("closedAt")
    cleanup = probe.get("cleanupAt")
    metrics = {
        "shellFeedback": probe.get("ariaVisibleAt") or probe.get("firstOpeningAt"),
        "stableVisual": probe.get("stableVisualAt"),
        "warmSummary": probe.get("warmSummaryAt"),
        "chartReady": probe.get("chartReadyAt"),
        "closeVisual": probe.get("closeVisualAt"),
        "cleanup": cleanup,
    }
    close_started = probe.get("closeRequestedAt")
    assessment: dict[str, dict[str, object]] = {}
    for name, measured_at in metrics.items():
        origin = close_started if name in {"closeVisual", "cleanup"} else started
        actual = round(float(measured_at) - float(origin), 2) if measured_at and origin else None
        budget = BRIEF_TIMING_BUDGETS_MS[name]
        assessment[name] = {
            "actualMs": actual,
            "budgetMs": budget,
            "withinBudget": actual is not None and budget is not None and actual <= budget,
            "progressiveOnly": name == "chartReady",
        }
    cleanup_budget = BRIEF_TIMING_BUDGETS_MS["cleanup"]
    assessment["lifecycleClosed"] = {
        "actualMs": round(float(closed) - float(close_started), 2) if closed and close_started else None,
        "budgetMs": cleanup_budget,
        "withinBudget": bool(
            closed and close_started and float(closed) - float(close_started) <= cleanup_budget
        ),
        "progressiveOnly": False,
    }
    return assessment


def record_viewport_screenshots(browser: object, url: str, output: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for width, height in VIEWPORTS.items():
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        install_runtime_observers(page)
        wait_ready(page, url)
        begin_runtime_measurement(page, f"drilldown:viewport-{width}-ready")
        contract = page_contract(page)
        if contract["overflow"] != 0 or contract["mains"] != 1 or contract["visibleH1s"] != 1:
            raise RuntimeError(f"Overview contract failed at {width}px: {contract}")
        screenshot = output / "screenshots" / f"overview-{width}.png"
        page.screenshot(path=screenshot, full_page=True, animations="disabled")
        results.append(
            {"width": width, "height": height, "contract": contract, "screenshot": str(screenshot)}
        )
        context.close()
    return results


def audit_lifecycle_and_interactions(browser: object, url: str, output: Path) -> dict[str, object]:
    video_dir = output / "recording"
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        record_video_dir=video_dir,
        record_video_size={"width": 1440, "height": 1000},
    )
    page = context.new_page()
    install_runtime_observers(page)
    browser_errors: list[str] = []
    server_errors: list[dict[str, object]] = []
    page.on("pageerror", lambda error: browser_errors.append(f"pageerror: {error}"))
    page.on(
        "console",
        lambda message: browser_errors.append(f"console: {message.text}")
        if message.type == "error"
        else None,
    )

    def response_observer(response: object) -> None:
        status = response.status
        if status >= 400:
            server_errors.append({"status": status, "path": safe_path(response.url)})

    page.on("response", response_observer)
    wait_ready(page, url)
    begin_runtime_measurement(page, "drilldown:lifecycle-ready")
    if page.locator(SHELL).count() != 1:
        raise RuntimeError("Expected one persistent detail shell before the first interaction")
    if overlay_state(page)["lifecycle"] != "closed":
        raise RuntimeError(f"Persistent shell was not closed at startup: {overlay_state(page)}")
    install_lifecycle_probe(page)
    result: dict[str, object] = {"initial": page_contract(page), "initialShell": overlay_state(page)}
    mark(page, "drilldown:first-open-click")
    page.locator(".city-movement").first.click()
    wait_lifecycle(page, "open", timeout=10_000)
    page.wait_for_function(
        """() => {
          const probe = window.__drilldownLifecycleProbe;
          return probe && probe.firstMetricAt !== null && probe.chartReadyAt !== null &&
            probe.stableVisualAt !== null;
        }""",
        timeout=30_000,
    )
    first_open = overlay_state(page)
    page.screenshot(path=output / "screenshots" / "drawer-open-1440.png", animations="disabled")

    close_button = page.locator("[data-detail-close]").first
    if not close_button.evaluate("node => node === document.activeElement"):
        raise RuntimeError("Drawer close control did not receive initial focus")
    if first_open["bodyOverflow"] != "hidden" or not first_open["scrollLock"]:
        raise RuntimeError(f"Drawer did not lock the document body: {first_open}")
    if int(first_open["inertMarkedNodes"]) < 1:
        raise RuntimeError(f"Drawer did not mark background content inert: {first_open}")

    page.evaluate("window.__drilldownLifecycleProbe.closeRequestedAt = performance.now()")
    mark(page, "drilldown:first-close-request")
    page.keyboard.press("Escape")
    wait_lifecycle(page, "closed", timeout=10_000)
    page.wait_for_function(
        """() => {
          const probe = window.__drilldownLifecycleProbe;
          return probe && probe.cleanupAt !== null;
        }""",
        timeout=10_000,
    )
    mark(page, "drilldown:first-close-cleanup")
    after_close = overlay_state(page)
    page.screenshot(path=output / "screenshots" / "drawer-closed-1440.png", animations="disabled")
    if after_close["bodyOverflow"] or after_close["scrollLock"] or after_close["inertMarkedNodes"]:
        raise RuntimeError(f"Drawer cleanup left document state behind: {after_close}")

    mark(page, "drilldown:second-open-click")
    page.locator(".city-movement").first.click()
    wait_lifecycle(page, "open", timeout=10_000)
    page.wait_for_function(
        """() => {
          const shell = document.querySelector('.city-detail-overlay[data-detail-overlay]');
          const drawer = shell && shell.querySelector('.city-detail-drawer');
          const title = drawer && drawer.querySelector('.city-detail-drawer__title');
          const currentTotal = drawer && drawer.querySelector('.city-detail-metrics .city-stat-card__value');
          return Boolean(title && title.textContent.trim() && currentTotal && currentTotal.textContent.trim());
        }""",
        timeout=20_000,
    )
    second_open = overlay_state(page)
    title_before_expand = str(second_open["title"])
    page.locator("[data-detail-expand]").first.click()
    page.locator("#overview-analysis-workspace").wait_for(state="visible", timeout=30_000)
    mark(page, "drilldown:workspace-visible")
    page.locator("#overview-analysis-workspace .city-movement").first.click()
    page.wait_for_function(
        """previous => {
          const title = document.querySelector('.city-detail-overlay:not([hidden]) .city-detail-drawer__title');
          return title && title.textContent.trim() !== previous;
        }""",
        arg=title_before_expand,
        timeout=30_000,
    )
    replacement = overlay_state(page)
    if first_open["activeOverlayId"] != replacement["activeOverlayId"]:
        raise RuntimeError(f"Persistent shell identity changed during hierarchy navigation: {replacement}")
    mark(page, "drilldown:second-close-request")
    page.keyboard.press("Escape")
    wait_lifecycle(page, "closed", timeout=10_000)

    recalculation_start = time.perf_counter()
    mark(page, "drilldown:recalculation-request")
    page.locator("#overview-flow").select_option("expense")
    page.wait_for_function(
        """() => {
          const flow = document.querySelector('#overview-flow');
          const section = document.querySelector("[data-view-section='overview']");
          return flow && flow.value === 'expense' && section && !section.querySelector('.recalculating');
        }""",
        timeout=30_000,
    )
    mark(page, "drilldown:recalculation-settled")
    recalculation_ms = round((time.perf_counter() - recalculation_start) * 1000, 2)
    probe = lifecycle_probe_report(page)
    if probe is None:
        raise RuntimeError("Lifecycle probe did not produce a report")
    result.update(
        {
            "drawer": {
                "firstOpen": first_open,
                "afterClose": after_close,
                "secondOpen": second_open,
                "afterHierarchyUpdate": replacement,
                "sameNodeOnReopen": first_open["activeOverlayId"] == second_open["activeOverlayId"],
                "sameNodeAfterHierarchyUpdate": second_open["activeOverlayId"]
                == replacement["activeOverlayId"],
                "identityChangedAfterHierarchyUpdate": second_open["title"] != replacement["title"],
                "shellReplacementCount": probe["shellCountAtEnd"] - probe["shellCountAtStart"],
                "shellIdentityRetained": probe["shellIdentityRetained"],
            },
            "acceptanceTimings": assess_lifecycle_timings(probe),
            "lifecycleProbe": probe,
            "outputRecalculation": {"selection": "expense", "settledMs": recalculation_ms},
            "final": page_contract(page),
            "runtime": runtime_metrics(page),
            "browserErrors": browser_errors,
            "serverErrors": server_errors,
        }
    )
    video = page.video
    context.close()
    if video is not None:
        result["recording"] = str(video.path())
    return result


def audit_keyboard_and_reduced_motion(browser: object, url: str) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    install_runtime_observers(page)
    wait_ready(page, url)
    begin_runtime_measurement(page, "drilldown:keyboard-ready")
    page.keyboard.press("Tab")
    skip_focused = page.locator(".skip-link").evaluate("node => node === document.activeElement")
    page.keyboard.press("Enter")
    main_focused = page.locator("#main").evaluate("node => node === document.activeElement")

    page.goto(f"{url.rstrip('/')}/#overview", wait_until="domcontentloaded")
    page.locator(".city-source-status--fresh").wait_for(state="visible", timeout=45_000)
    page.emulate_media(reduced_motion="reduce")
    begin_runtime_measurement(page, "drilldown:reduced-motion-ready")
    page.locator(".city-movement").first.click()
    page.get_by_role("dialog").wait_for(state="visible", timeout=30_000)
    drawer = page.locator(".city-detail-drawer").first
    page.keyboard.down("Shift")
    page.keyboard.press("Tab")
    page.keyboard.up("Shift")
    focus_after_reverse_tab = page.evaluate(
        "Boolean(document.activeElement && document.activeElement.closest('.city-detail-drawer'))"
    )
    page.keyboard.press("Tab")
    close_refocused = page.locator("[data-detail-close]").first.evaluate(
        "node => node === document.activeElement"
    )
    motion = drawer.evaluate(
        """node => {
          const style = window.getComputedStyle(node);
          return {
            reducedMotionMatched: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
            transitionDuration: style.transitionDuration,
            animationDuration: style.animationDuration
          };
        }"""
    )
    page.keyboard.press("Escape")
    page.get_by_role("dialog").wait_for(state="hidden", timeout=20_000)
    result = {
        "skipLinkFocused": skip_focused,
        "mainFocusedAfterSkip": main_focused,
        "focusStayedInDrawerAfterReverseTab": focus_after_reverse_tab,
        "closeRefocusedAfterTab": close_refocused,
        "reducedMotion": motion,
        "final": page_contract(page),
        "runtime": runtime_metrics(page),
    }
    context.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/ui-audit/drilldown-follow-up/baseline"),
    )
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "screenshots").mkdir(parents=True, exist_ok=True)
    (args.output / "recording").mkdir(parents=True, exist_ok=True)
    runtime_temp = args.output / "runtime-temp"
    runtime_temp.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        {
            "TEMP": str(runtime_temp),
            "TMP": str(runtime_temp),
            "TMPDIR": str(runtime_temp),
        }
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        result = {
            "target": safe_path(args.url),
            "screenshots": record_viewport_screenshots(browser, args.url, args.output),
            "lifecycle": audit_lifecycle_and_interactions(browser, args.url, args.output),
            "keyboardAndReducedMotion": audit_keyboard_and_reduced_motion(browser, args.url),
        }
        browser.close()
    metrics = args.output / "runtime-metrics.json"
    metrics.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote runtime audit evidence to {metrics}")


if __name__ == "__main__":
    try:
        main()
    except TimeoutError as error:
        raise SystemExit(f"Audit timed out: {error}") from error
