"""Contract tests for the persistent, integrated budget-detail drawer shell."""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

pytestmark = pytest.mark.e2e

SHELL = ".city-detail-overlay[data-detail-overlay]"
DRAWER = f"{SHELL} .city-detail-drawer"
OVERVIEW_QUIESCENCE_MS = 2_000
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def ready(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded")
    expect(page.locator(".city-source-status--fresh")).to_be_visible(timeout=45_000)
    expect(page.locator("[data-view-section='overview']")).to_be_visible(timeout=30_000)
    page.wait_for_function(
        """() => !document.querySelector("[data-view-section='overview'] .recalculating")""",
        timeout=30_000,
    )


def shell_state(page: Page) -> dict[str, object]:
    return page.locator(SHELL).evaluate(
        """shell => ({
          lifecycle: shell.getAttribute('data-detail-lifecycle'),
          ariaHidden: shell.getAttribute('aria-hidden'),
          bodyOverflow: document.body.style.overflow,
          scrollLock: document.body.getAttribute('data-city-scroll-lock'),
          inertMarkedNodes: document.querySelectorAll('[data-city-inert-before]').length,
          openDialogs: Array.from(document.querySelectorAll('[role="dialog"]')).filter(node => {
            const style = window.getComputedStyle(node);
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              node.getBoundingClientRect().width > 0;
          }).length
        })"""
    )


def wait_lifecycle(page: Page, value: str) -> None:
    expect(page.locator(SHELL)).to_have_attribute("data-detail-lifecycle", value, timeout=10_000)


def wait_drawer_values(page: Page) -> None:
    page.wait_for_function(
        """() => {
          const drawer = document.querySelector('.city-detail-overlay[data-detail-overlay] .city-detail-drawer');
          const title = drawer && drawer.querySelector('.city-detail-drawer__title');
          const total = drawer && drawer.querySelector('.city-detail-metrics .city-stat-card__value');
          const amount = drawer && drawer.querySelector('.city-detail-change__amount');
          const percent = drawer && drawer.querySelector('.city-detail-change__percent');
          return Boolean(title && title.textContent.trim() && total && total.textContent.trim() &&
            amount && amount.textContent.trim() && percent && percent.textContent.trim());
        }""",
        timeout=30_000,
    )


def wait_overview_settled(page: Page) -> None:
    page.wait_for_function(
        """() => !document.querySelector("[data-view-section='overview'] .recalculating")""",
        timeout=30_000,
    )


def open_drawer(page: Page) -> tuple[float, str]:
    trigger = page.locator(".city-movement").first
    started = time.perf_counter()
    trigger.click()
    wait_lifecycle(page, "open")
    expect(page.locator(DRAWER)).to_be_visible(timeout=10_000)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 4_000, f"drawer open exceeded the tolerant 4-second ceiling: {elapsed_ms:.0f} ms"
    wait_drawer_values(page)
    title = page.locator(f"{DRAWER} .city-detail-drawer__title").inner_text()
    return elapsed_ms, title


def close_drawer(page: Page) -> float:
    started = time.perf_counter()
    page.keyboard.press("Escape")
    wait_lifecycle(page, "closed")
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 2_000, f"drawer close exceeded the tolerant 2-second ceiling: {elapsed_ms:.0f} ms"
    return elapsed_ms


def assert_root_has_no_overflow(page: Page) -> None:
    metrics = page.evaluate(
        """() => ({
          rootOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          bodyOverflow: document.body.scrollWidth - document.body.clientWidth
        })"""
    )
    assert metrics["rootOverflow"] == 0, metrics
    assert metrics["bodyOverflow"] == 0, metrics


def assert_closed_cleanup(page: Page, trigger: object | None = None) -> None:
    state = shell_state(page)
    assert state["lifecycle"] == "closed", state
    assert state["ariaHidden"] == "true", state
    assert state["bodyOverflow"] == "", state
    assert state["scrollLock"] is None, state
    assert state["inertMarkedNodes"] == 0, state
    assert state["openDialogs"] == 0, state
    if trigger is not None:
        descriptor = trigger.evaluate(
            """node => Object.fromEntries(
              Array.from(node.attributes)
                .filter(attribute => attribute.name.startsWith('data-selection-'))
                .map(attribute => [attribute.name, attribute.value])
            )"""
        )
        page.wait_for_function(
            "() => document.activeElement && document.activeElement !== document.body",
            timeout=2_000,
        )
        focus_state = page.evaluate(
            """expected => {
              const active = document.activeElement;
              if (!active) return { valid: false, active: null };
              const matchingMovement = active.matches('.city-movement') && Object.entries(expected)
                .every(([name, value]) => active.getAttribute(name) === value);
              const stableFallback = active.id === 'overview-analysis-workspace' || active.id === 'main';
              const inPersistentOverview = active.closest('#overview-analysis-workspace, #main') !== null
                && !active.closest('[data-detail-overlay]');
              return {
                valid: matchingMovement || stableFallback || inPersistentOverview,
                active: active.outerHTML.slice(0, 500),
              };
            }""",
            arg=descriptor,
        )
        assert focus_state["valid"], focus_state


def record_shell_and_background_identity(page: Page) -> None:
    page.evaluate(
        """() => {
          const selectors = [
            '.city-detail-overlay[data-detail-overlay]',
            'header',
            'main',
            "[data-view-section='overview']",
            '#overview-trend_chart',
            '#overview-movements'
          ];
          window.__drawerContractReferences = Object.fromEntries(
            selectors.map(selector => [selector, document.querySelector(selector)])
          );
          window.__drawerContractOverviewRecalculations = 0;
          const overview = document.querySelector("[data-view-section='overview']");
          window.__drawerContractObserver = new MutationObserver(records => {
            for (const record of records) {
              const target = record.target;
              if (target instanceof Element && target.classList.contains('recalculating')) {
                window.__drawerContractOverviewRecalculations += 1;
              }
            }
          });
          window.__drawerContractObserver.observe(overview, {
            attributes: true,
            attributeFilter: ['class'],
            subtree: true
          });
        }"""
    )


def identity_and_recalculation_report(page: Page) -> dict[str, object]:
    return page.evaluate(
        """() => {
          const refs = window.__drawerContractReferences;
          const identities = Object.fromEntries(
            Object.keys(refs).map(selector => [selector, refs[selector] === document.querySelector(selector)])
          );
          const background = document.querySelector("[data-view-section='overview']");
          return {
            identities,
            overviewRecalculations: window.__drawerContractOverviewRecalculations,
            overviewOpacity: background ? window.getComputedStyle(background).opacity : null,
            overviewBusy: Boolean(background && background.querySelector('.recalculating')),
            shellCount: document.querySelectorAll('.city-detail-overlay[data-detail-overlay]').length
          };
        }"""
    )


def reset_overview_recalculation_counter(page: Page) -> None:
    page.evaluate("window.__drawerContractOverviewRecalculations = 0")


def test_persistent_shell_keeps_identity_and_semantic_change_values(page: Page, live_server_url: str) -> None:
    ready(page, live_server_url)
    shell = page.locator(SHELL)
    expect(shell).to_have_count(1)
    expect(shell).to_have_attribute("data-detail-lifecycle", "closed")
    expect(shell).to_have_attribute("aria-hidden", "true")
    expect(shell.locator(".city-detail-drawer")).to_have_count(1)
    record_shell_and_background_identity(page)

    trigger = page.locator(".city-movement").first
    open_drawer(page)
    expect(shell).to_have_attribute("aria-hidden", "false")
    expect(page.locator(f"{DRAWER} .city-detail-change__amount").first).not_to_be_empty()
    expect(page.locator(f"{DRAWER} .city-detail-change__percent").first).not_to_be_empty()

    close_drawer(page)
    assert_closed_cleanup(page, trigger)
    page.wait_for_timeout(OVERVIEW_QUIESCENCE_MS)
    wait_overview_settled(page)
    report = identity_and_recalculation_report(page)
    assert all(report["identities"].values()), report
    assert report["overviewRecalculations"] == 0, report
    assert report["overviewOpacity"] == "1", report
    assert not report["overviewBusy"], report
    assert report["shellCount"] == 1, report


def test_same_context_reopen_keeps_background_stable_without_overview_recalculation(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    record_shell_and_background_identity(page)
    trigger = page.locator(".city-movement").first
    _, first_title = open_drawer(page)
    close_drawer(page)
    assert_closed_cleanup(page, trigger)
    expect(trigger).to_have_class(re.compile(r"\bis-selected\b"), timeout=30_000)
    wait_overview_settled(page)
    reset_overview_recalculation_counter(page)
    _, second_title = open_drawer(page)
    assert second_title == first_title
    close_drawer(page)
    assert_closed_cleanup(page, trigger)
    report = identity_and_recalculation_report(page)
    assert all(report["identities"].values()), report
    assert report["overviewRecalculations"] == 0, report
    assert report["overviewOpacity"] == "1", report
    assert report["shellCount"] == 1, report


def test_rapid_open_close_open_and_repeated_cycles_leave_one_clean_shell(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    shell = page.locator(SHELL)
    trigger = page.locator(".city-movement").first
    trigger.click()
    page.keyboard.press("Escape")
    trigger.click()
    wait_lifecycle(page, "open")
    expect(shell).to_have_count(1)
    expect(shell).to_have_attribute("aria-hidden", "false")
    close_drawer(page)
    assert_closed_cleanup(page, trigger)

    for _ in range(5):
        open_drawer(page)
        close_drawer(page)
        assert_closed_cleanup(page, trigger)
    expect(shell).to_have_count(1)
    assert_root_has_no_overflow(page)


def test_replaced_origin_closes_to_visible_fallback_without_late_focus_theft(
    page: Page, live_server_url: str
) -> None:
    """Cover the replacement window between a close and deferred focus recovery."""
    ready(page, live_server_url)
    trigger = page.locator(".city-movement").first
    descriptor = trigger.evaluate(
        """node => Object.fromEntries(
          Array.from(node.attributes)
            .filter(attribute => attribute.name.startsWith('data-selection-'))
            .map(attribute => [attribute.name, attribute.value])
        )"""
    )
    open_drawer(page)
    removed = page.evaluate(
        """expected => {
          const matches = Array.from(document.querySelectorAll('[data-overview-select]')).filter(node =>
            Object.entries(expected).every(([name, value]) => node.getAttribute(name) === value)
          );
          matches.forEach(node => node.remove());
          return matches.length;
        }""",
        arg=descriptor,
    )
    assert removed > 0

    close_drawer(page)
    assert_closed_cleanup(page)
    page.wait_for_function(
        """() => {
          const active = document.activeElement;
          return Boolean(active && !active.closest('[data-detail-overlay]'));
        }""",
        timeout=2_000,
    )
    page.wait_for_function(
        """() => {
          const active = document.activeElement;
          return Boolean(active && (active.id === 'overview-analysis-workspace' || active.id === 'main'));
        }""",
        timeout=2_000,
    )
    fallback_id = page.evaluate("() => document.activeElement && document.activeElement.id")
    assert fallback_id in {"overview-analysis-workspace", "main"}

    page.evaluate(
        """expected => {
          const host = document.querySelector('#overview-movements .city-movement-list') ||
            document.querySelector('[data-view-section="overview"] .city-movement-list');
          if (!host) throw new Error('Movement host is not available');
          const replacement = document.createElement('button');
          replacement.type = 'button';
          replacement.className = 'city-movement';
          replacement.setAttribute('data-overview-select', 'true');
          replacement.setAttribute('aria-label', 'Replacement movement');
          Object.entries(expected).forEach(([name, value]) => replacement.setAttribute(name, value));
          replacement.textContent = 'Replacement movement';
          host.append(replacement);
        }""",
        arg=descriptor,
    )
    page.wait_for_timeout(750)
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == fallback_id


def test_close_opacity_is_nonincreasing_until_the_persistent_shell_is_hidden(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    open_drawer(page)
    page.wait_for_function(
        """() => {
          const shell = document.querySelector('.city-detail-overlay[data-detail-overlay]');
          return shell && shell.getAttribute('data-detail-lifecycle') === 'open' &&
            Number(window.getComputedStyle(shell).opacity) >= 0.99;
        }"""
    )
    page.locator(SHELL).evaluate(
        """shell => {
          window.__drawerContractOpacity = [];
          const record = () => {
            window.__drawerContractOpacity.push(Number(window.getComputedStyle(shell).opacity));
            if (window.__drawerContractOpacity.length < 90) requestAnimationFrame(record);
          };
          requestAnimationFrame(record);
        }"""
    )
    close_drawer(page)
    page.wait_for_timeout(100)
    opacities = page.evaluate("window.__drawerContractOpacity")
    assert len(opacities) >= 2, opacities
    assert opacities[-1] <= opacities[0], opacities
    assert all(
        next_value <= value + 0.02 for value, next_value in zip(opacities, opacities[1:], strict=False)
    ), opacities


def test_hierarchy_and_browser_back_close_the_same_shell_without_duplicates(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    shell = page.locator(SHELL)
    _, first_title = open_drawer(page)
    page.locator(f"{DRAWER} [data-detail-expand]").click()
    workspace = page.locator("#overview-analysis-workspace")
    expect(workspace).to_be_visible(timeout=20_000)
    workspace.locator(".city-movement").first.click()
    page.wait_for_function(
        """previous => {
          const title = document.querySelector(
            '.city-detail-overlay[data-detail-overlay] .city-detail-drawer__title'
          );
          return title && title.textContent.trim() !== previous;
        }""",
        arg=first_title,
        timeout=20_000,
    )
    wait_lifecycle(page, "open")
    expect(shell).to_have_count(1)

    page.locator(f"{DRAWER} [data-detail-back]").click()
    page.wait_for_function(
        """expected => {
          const title = document.querySelector(
            '.city-detail-overlay[data-detail-overlay] .city-detail-drawer__title'
          );
          return title && title.textContent.trim() === expected;
        }""",
        arg=first_title,
        timeout=20_000,
    )
    wait_lifecycle(page, "open")
    close_drawer(page)
    expect(shell).to_have_count(1)
    assert_closed_cleanup(page)


def test_bookmark_restored_open_drawer_preserves_shell_and_close_cleanup(
    page: Page, live_server_url: str
) -> None:
    ready(page, live_server_url)
    open_drawer(page)
    page.locator(f"{DRAWER} [data-detail-copy]").click()
    expect(page).to_have_url(re.compile(r"_inputs_"), timeout=20_000)
    bookmarked = page.url

    restored = page.context.new_page()
    try:
        restored.goto(bookmarked, wait_until="domcontentloaded")
        expect(restored.locator(".city-source-status--fresh")).to_be_visible(timeout=45_000)
        expect(restored.locator(SHELL)).to_have_count(1)
        wait_lifecycle(restored, "open")
        restored.keyboard.press("Escape")
        wait_lifecycle(restored, "closed")
        assert_closed_cleanup(restored)
    finally:
        restored.close()


def test_reduced_motion_keyboard_focus_and_cleanup(page: Page, live_server_url: str) -> None:
    page.emulate_media(reduced_motion="reduce")
    ready(page, live_server_url)
    page.keyboard.press("Tab")
    assert page.locator(".skip-link").evaluate("node => node === document.activeElement")
    page.keyboard.press("Enter")
    assert page.locator("#main").evaluate("node => node === document.activeElement")

    page.goto(live_server_url, wait_until="domcontentloaded")
    expect(page.locator(".city-source-status--fresh")).to_be_visible(timeout=45_000)
    trigger = page.locator(".city-movement").first
    open_drawer(page)
    drawer = page.locator(DRAWER)
    motion = drawer.evaluate(
        """node => ({
          matched: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
          transition: window.getComputedStyle(node).transitionDuration,
          animation: window.getComputedStyle(node).animationDuration
        })"""
    )
    assert motion["matched"], motion
    assert all(float(value.replace("s", "")) <= 0.01 for value in motion["transition"].split(", "))
    assert all(float(value.replace("s", "")) <= 0.01 for value in motion["animation"].split(", "))
    page.keyboard.down("Shift")
    page.keyboard.press("Tab")
    page.keyboard.up("Shift")
    assert page.evaluate(
        "Boolean(document.activeElement && document.activeElement.closest('.city-detail-drawer'))"
    )
    page.keyboard.press("Tab")
    assert page.locator(f"{DRAWER} [data-detail-close]").first.evaluate(
        "node => node === document.activeElement"
    )
    close_drawer(page)
    assert_closed_cleanup(page, trigger)


@pytest.mark.parametrize("width", (390, 768, 1024, 1440, 1920))
def test_shell_metrics_and_long_change_values_fit_every_required_width(
    page: Page, live_server_url: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 1080})
    ready(page, live_server_url)
    assert_root_has_no_overflow(page)
    movement_index = page.locator(".city-movement").evaluate_all(
        """nodes => nodes.reduce((longest, node, index) =>
          node.textContent.trim().length > nodes[longest].textContent.trim().length ? index : longest, 0)"""
    )
    page.locator(".city-movement").nth(movement_index).click()
    wait_lifecycle(page, "open")
    wait_drawer_values(page)
    metrics = page.locator(DRAWER).evaluate(
        """drawer => {
          const rect = drawer.getBoundingClientRect();
          const values = Array.from(drawer.querySelectorAll(
            '.city-detail-change__amount, .city-detail-change__percent'
          ));
          const metricContainers = Array.from(drawer.querySelectorAll(
            '.city-detail-change, .city-detail-metric, .city-detail-change__amount, ' +
            '.city-detail-change__percent'
          )).map(node => ({
            label: node.className,
            scrollWidth: node.scrollWidth,
            clientWidth: node.clientWidth
          }));
          return {
            drawerLeft: rect.left,
            drawerRight: rect.right,
            viewportWidth: window.innerWidth,
            longestValue: Math.max(0, ...values.map(node => node.textContent.trim().length)),
            metricContainers,
            overflowingValue: values.some(node => {
              const valueRect = node.getBoundingClientRect();
              return valueRect.left < -1 || valueRect.right > window.innerWidth + 1;
            })
          };
        }"""
    )
    assert metrics["drawerLeft"] >= -1, metrics
    assert metrics["drawerRight"] <= metrics["viewportWidth"] + 1, metrics
    assert metrics["longestValue"] >= 4, metrics
    assert not metrics["overflowingValue"], metrics
    assert metrics["metricContainers"], metrics
    assert all(
        container["scrollWidth"] <= container["clientWidth"] for container in metrics["metricContainers"]
    ), metrics
    close_drawer(page)
    assert_root_has_no_overflow(page)


@contextmanager
def ten_contexts(browser: Browser) -> Iterator[tuple[list[BrowserContext], list[Page]]]:
    contexts: list[BrowserContext] = []
    pages: list[Page] = []
    try:
        for _ in range(10):
            context = browser.new_context(viewport={"width": 1024, "height": 900})
            contexts.append(context)
            pages.append(context.new_page())
        yield contexts, pages
    finally:
        for context in contexts:
            context.close()


def test_ten_sessions_keep_overview_and_drawer_state_isolated(browser: Browser, live_server_url: str) -> None:
    with ten_contexts(browser) as (_, pages):
        for session in pages:
            ready(session, live_server_url)
            expect(session.locator(SHELL)).to_have_count(1)
            wait_lifecycle(session, "closed")
        pages[0].locator("#overview-flow").select_option("expense")
        pages[0].locator(".city-movement").first.click()
        wait_lifecycle(pages[0], "open")
        for session in pages[1:]:
            expect(session.locator("#overview-flow")).to_have_value("all", timeout=20_000)
            wait_lifecycle(session, "closed")


def test_detail_runtime_does_not_attach_a_body_wide_mutation_observer() -> None:
    source = (PROJECT_ROOT / "www" / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"\.observe\(\s*document\.body\b", source), (
        "The drawer runtime must not use a body-wide MutationObserver. Keep lifecycle control scoped "
        "to the persistent detail shell."
    )
