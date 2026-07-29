"""Measure Shiny 1.7 startup, data paths, browser timing, sockets, and memory.

All app launches are local automated test launches with SHINY_TESTMODE=1.
The script never changes the production App configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

import psutil
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STALE_URL = "http://127.0.0.1:9/unavailable/FeatureServer/0"


def safe_url(value: str) -> str:
    parts = urlsplit(value)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def process_tree_memory(root_pid: int) -> dict[str, int]:
    try:
        root = psutil.Process(root_pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        return {"processes": 0, "rss_bytes": 0, "private_bytes": 0}
    rss = 0
    private = 0
    counted = 0
    for process in processes:
        try:
            info = process.memory_full_info()
        except psutil.Error:
            continue
        rss += int(info.rss)
        private += int(getattr(info, "uss", info.rss))
        counted += 1
    return {"processes": counted, "rss_bytes": rss, "private_bytes": private}


@dataclass
class LocalServer:
    label: str
    output: Path
    cache_dir: Path
    extra_env: dict[str, str]
    port: int = 0
    process: subprocess.Popen[bytes] | None = None
    stdout_handle: Any = None
    stderr_handle: Any = None
    http_ready_ms: float | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout_seconds: float = 45.0) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.port = free_port()
        shiny = Path(sys.executable).with_name("shiny.exe")
        self.stdout_handle = (self.output / "server.stdout.log").open("wb")
        self.stderr_handle = (self.output / "server.stderr.log").open("wb")
        environment = {
            **os.environ,
            "SHINY_TESTMODE": "1",
            "BUDGET_CACHE_DIR": str(self.cache_dir),
            **self.extra_env,
        }
        command = [
            str(shiny),
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "app.py",
        ]
        started = time.perf_counter()
        self.process = subprocess.Popen(  # noqa: S603
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=self.stdout_handle,
            stderr=self.stderr_handle,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = started + timeout_seconds
        while time.perf_counter() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"{self.label} server exited before HTTP readiness")
            try:
                with urlopen(self.url, timeout=1) as response:  # noqa: S310
                    if response.status == 200:
                        self.http_ready_ms = round((time.perf_counter() - started) * 1000, 2)
                        return
            except (OSError, URLError):
                pass
            time.sleep(0.05)
        raise RuntimeError(f"{self.label} server did not become HTTP ready")

    def memory(self) -> dict[str, int]:
        if self.process is None:
            return {"processes": 0, "rss_bytes": 0, "private_bytes": 0}
        return process_tree_memory(self.process.pid)

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        for handle in (self.stdout_handle, self.stderr_handle):
            if handle is not None:
                handle.close()


def new_network_log() -> dict[str, Any]:
    return {
        "console": [],
        "page_errors": [],
        "failed_requests": [],
        "http_errors": [],
        "websockets": [],
    }


def observe_page(page: Page, events: dict[str, Any]) -> None:
    page.on(
        "console",
        lambda message: events["console"].append({"type": message.type, "text": message.text[:1000]})
        if message.type in {"warning", "error"}
        else None,
    )
    page.on("pageerror", lambda error: events["page_errors"].append(str(error)[:1000]))
    page.on(
        "requestfailed",
        lambda request: events["failed_requests"].append(
            {
                "method": request.method,
                "url": safe_url(request.url),
                "failure": request.failure,
            }
        ),
    )
    page.on(
        "response",
        lambda response: events["http_errors"].append(
            {
                "status": response.status,
                "method": response.request.method,
                "url": safe_url(response.url),
            }
        )
        if response.status >= 400
        else None,
    )

    def on_websocket(websocket: Any) -> None:
        record: dict[str, Any] = {
            "url": safe_url(websocket.url),
            "frames_sent": 0,
            "frames_received": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "closed": False,
            "errors": [],
        }
        events["websockets"].append(record)

        def payload_size(payload: Any) -> int:
            if isinstance(payload, bytes):
                return len(payload)
            return len(str(payload).encode("utf-8"))

        websocket.on(
            "framesent",
            lambda payload: (
                record.__setitem__("frames_sent", record["frames_sent"] + 1),
                record.__setitem__("bytes_sent", record["bytes_sent"] + payload_size(payload)),
            ),
        )
        websocket.on(
            "framereceived",
            lambda payload: (
                record.__setitem__("frames_received", record["frames_received"] + 1),
                record.__setitem__(
                    "bytes_received",
                    record["bytes_received"] + payload_size(payload),
                ),
            ),
        )
        websocket.on("close", lambda: record.__setitem__("closed", True))
        websocket.on(
            "socketerror",
            lambda error: record["errors"].append(str(error)[:1000]),
        )

    page.on("websocket", on_websocket)


async def wait_for_overview_ready(page: Page, status_class: str, timeout_ms: int) -> None:
    await page.locator(status_class).wait_for(state="visible", timeout=timeout_ms)
    await page.locator("[data-view-section='overview'] h1").wait_for(state="visible", timeout=timeout_ms)
    await page.wait_for_function(
        """() => {
          const section = document.querySelector("[data-view-section='overview']");
          return section && !section.querySelector(".recalculating") &&
            Boolean(section.querySelector(".city-stat-card, .city-movement"));
        }""",
        timeout=timeout_ms,
    )


async def measure_page(
    browser: Browser,
    server: LocalServer,
    output: Path,
    *,
    label: str,
    status_class: str,
    timeout_ms: int,
    exercise: bool,
) -> dict[str, Any]:
    context = await browser.new_context(viewport={"width": 1440, "height": 1000})
    await context.add_init_script(
        """
        (() => {
          window.__budgetPerf = { mutations: 0, longTasks: [] };
          const start = () => {
            new MutationObserver((records) => {
              window.__budgetPerf.mutations += records.length;
            }).observe(document.documentElement, {
              attributes: true,
              childList: true,
              characterData: true,
              subtree: true
            });
          };
          if (document.documentElement) start();
          else document.addEventListener("DOMContentLoaded", start, { once: true });
          try {
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries()) {
                window.__budgetPerf.longTasks.push(Number(entry.duration.toFixed(2)));
              }
            }).observe({ type: "longtask", buffered: true });
          } catch (_error) {
            // Long-task timing is optional in browsers that do not expose it.
          }
        })();
        """
    )
    await context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = await context.new_page()
    events = new_network_log()
    observe_page(page, events)
    started = time.perf_counter()
    response = await page.goto(server.url, wait_until="domcontentloaded", timeout=timeout_ms)
    dom_content_loaded_ms = round((time.perf_counter() - started) * 1000, 2)
    if response is None or not response.ok:
        status = response.status if response is not None else "no response"
        raise RuntimeError(f"{label} navigation failed with status {status}")
    await wait_for_overview_ready(page, status_class, timeout_ms)
    first_useful_ms = round((time.perf_counter() - started) * 1000, 2)

    chart_started = time.perf_counter()
    chart_ready = True
    try:
        await page.wait_for_function(
            """() => {
              const plot = document.querySelector("#overview-trend_chart .js-plotly-plot");
              return plot && plot.querySelectorAll(".main-svg").length > 0 &&
                plot.querySelectorAll(".barlayer path, .scatterlayer path, .point").length > 0;
            }""",
            timeout=timeout_ms,
        )
    except Exception:
        chart_ready = False
    chart_ready_ms = round((time.perf_counter() - chart_started) * 1000, 2)

    interaction: dict[str, Any] = {}
    if exercise and status_class.endswith("--fresh"):
        changed_started = time.perf_counter()
        await page.locator('[data-nav-value="changed"]').first.click()
        await page.locator("[data-view-section='changed'] h1").wait_for(state="visible", timeout=timeout_ms)
        interaction["changed_navigation_ms"] = round((time.perf_counter() - changed_started) * 1000, 2)

        explorer_started = time.perf_counter()
        await page.locator('[data-nav-value="explorer"]').first.click()
        await page.locator("#explorer-table tbody tr").first.wait_for(state="visible", timeout=timeout_ms)
        interaction["explorer_first_grid_ms"] = round((time.perf_counter() - explorer_started) * 1000, 2)

        summary = page.locator("#explorer-summary")
        before_summary = await summary.inner_text()
        filter_started = time.perf_counter()
        await page.locator("#explorer-flow").select_option("expense")
        await page.wait_for_function(
            """before => {
              const summary = document.querySelector("#explorer-summary");
              const view = document.querySelector("[data-view-section='explorer']");
              return summary && summary.textContent.trim() !== before &&
                view && !view.querySelector(".recalculating");
            }""",
            arg=before_summary.strip(),
            timeout=timeout_ms,
        )
        interaction["explorer_filter_settled_ms"] = round((time.perf_counter() - filter_started) * 1000, 2)

    await page.screenshot(path=output / f"{label}.png", full_page=True, animations="disabled")
    resources = await page.evaluate(
        """() => performance.getEntriesByType("resource").map(entry => ({
          name: (() => {
            const url = new URL(entry.name);
            return url.origin + url.pathname;
          })(),
          initiatorType: entry.initiatorType,
          durationMs: Number(entry.duration.toFixed(2)),
          transferSize: entry.transferSize,
          encodedBodySize: entry.encodedBodySize
        }))"""
    )
    navigation = await page.evaluate(
        """() => {
          const entry = performance.getEntriesByType("navigation")[0];
          return entry ? {
            responseStartMs: Number(entry.responseStart.toFixed(2)),
            domContentLoadedMs: Number(entry.domContentLoadedEventEnd.toFixed(2)),
            loadEventEndMs: Number(entry.loadEventEnd.toFixed(2)),
            durationMs: Number(entry.duration.toFixed(2))
          } : null;
        }"""
    )
    runtime = await page.evaluate(
        """() => ({
          mutations: window.__budgetPerf ? window.__budgetPerf.mutations : null,
          longTasksMs: window.__budgetPerf ? window.__budgetPerf.longTasks : [],
          longestLongTaskMs: window.__budgetPerf && window.__budgetPerf.longTasks.length
            ? Math.max(...window.__budgetPerf.longTasks)
            : 0
        })"""
    )
    await context.tracing.stop(path=output / f"{label}-trace.zip")
    await context.close()
    return {
        "label": label,
        "status_class": status_class,
        "dom_content_loaded_ms": dom_content_loaded_ms,
        "first_useful_ms": first_useful_ms,
        "chart_ready": chart_ready,
        "chart_ready_after_useful_ms": chart_ready_ms,
        "interaction": interaction,
        "navigation": navigation,
        "runtime": runtime,
        "resources": resources,
        "events": events,
    }


async def open_ready_session(
    browser: Browser, url: str, timeout_ms: int
) -> tuple[BrowserContext, Page, float]:
    context = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await context.new_page()
    started = time.perf_counter()
    response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    if response is None or not response.ok:
        await context.close()
        status = response.status if response is not None else "no response"
        raise RuntimeError(f"Ten-session navigation failed with status {status}")
    await wait_for_overview_ready(page, ".city-source-status--fresh", timeout_ms)
    return context, page, round((time.perf_counter() - started) * 1000, 2)


async def ten_session_memory(browser: Browser, server: LocalServer, timeout_ms: int) -> dict[str, Any]:
    before = server.memory()
    results = await asyncio.gather(
        *(open_ready_session(browser, server.url, timeout_ms) for _ in range(10)),
        return_exceptions=True,
    )
    opened: list[tuple[BrowserContext, Page, float]] = []
    failures: list[str] = []
    for result in results:
        if isinstance(result, BaseException):
            failures.append(str(result))
        else:
            opened.append(result)
    after_ready = server.memory()
    isolated = False
    if len(opened) == 10:
        first_page = opened[0][1]
        await first_page.locator("#overview-flow").select_option("expense")
        await first_page.locator("#overview-flow").wait_for(state="visible")
        await first_page.wait_for_function(
            """() => {
              const flow = document.querySelector("#overview-flow");
              const view = document.querySelector("[data-view-section='overview']");
              return flow && flow.value === "expense" &&
                view && !view.querySelector(".recalculating");
            }""",
            timeout=timeout_ms,
        )
        values = await asyncio.gather(
            *(page.locator("#overview-flow").input_value() for _, page, _ in opened[1:])
        )
        isolated = all(value == "all" for value in values)
    await asyncio.gather(
        *(context.close() for context, _, _ in opened),
        return_exceptions=True,
    )
    samples: list[dict[str, int]] = []
    deadline = time.perf_counter() + 5
    while time.perf_counter() < deadline:
        current = server.memory()
        samples.append(current)
        if len(samples) >= 3:
            recent = [sample["private_bytes"] for sample in samples[-3:]]
            if max(recent) - min(recent) < 1024 * 1024:
                break
        await asyncio.sleep(0.2)
    return {
        "before": before,
        "after_ready": after_ready,
        "after_close": samples[-1] if samples else server.memory(),
        "ready_sessions": len(opened),
        "ready_ms": [value for _, _, value in opened],
        "failures": failures,
        "session_state_isolated": isolated,
        "settle_samples": samples,
    }


def cache_evidence(cache_dir: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for path in sorted(cache_dir.glob("approved-budgets.*")):
        evidence.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return evidence


async def run(output: Path, channel: str | None, timeout_ms: int) -> dict[str, Any]:
    if (output / "metrics.json").exists():
        raise RuntimeError(f"Refusing to overwrite existing metrics: {output / 'metrics.json'}")
    output.mkdir(parents=True, exist_ok=True)
    cache_dir = output / "cache"
    result: dict[str, Any] = {
        "test_mode_only": True,
        "project_root": str(PROJECT_ROOT),
        "cache_dir": str(cache_dir),
    }
    launch_options: dict[str, Any] = {"headless": True}
    if channel:
        launch_options["channel"] = channel

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**launch_options)
        cold = LocalServer("cold", output / "cold", cache_dir, {})
        try:
            cold.start(timeout_seconds=max(45, timeout_ms / 1000))
            result["cold_http_ready_ms"] = cold.http_ready_ms
            result["cold_memory_before_session"] = cold.memory()
            result["cold_arcgis"] = await measure_page(
                browser,
                cold,
                output / "cold",
                label="cold-arcgis",
                status_class=".city-source-status--fresh",
                timeout_ms=timeout_ms,
                exercise=True,
            )
            result["warm_in_process"] = await measure_page(
                browser,
                cold,
                output / "cold",
                label="warm-in-process",
                status_class=".city-source-status--fresh",
                timeout_ms=timeout_ms,
                exercise=False,
            )
            result["ten_sessions"] = await ten_session_memory(browser, cold, timeout_ms)
            result["cache_after_cold"] = cache_evidence(cache_dir)
        finally:
            cold.stop()

        warm = LocalServer("warm-restart", output / "warm-restart", cache_dir, {})
        try:
            warm.start(timeout_seconds=max(45, timeout_ms / 1000))
            result["warm_restart_http_ready_ms"] = warm.http_ready_ms
            result["warm_restart"] = await measure_page(
                browser,
                warm,
                output / "warm-restart",
                label="warm-restart",
                status_class=".city-source-status--fresh",
                timeout_ms=timeout_ms,
                exercise=True,
            )
        finally:
            warm.stop()

        stale = LocalServer(
            "stale",
            output / "stale",
            cache_dir,
            {
                "BUDGET_ARCGIS_URL": DEFAULT_STALE_URL,
                "BUDGET_CACHE_TTL_SECONDS": "1",
            },
        )
        try:
            stale.start(timeout_seconds=max(45, timeout_ms / 1000))
            result["stale_http_ready_ms"] = stale.http_ready_ms
            result["stale"] = await measure_page(
                browser,
                stale,
                output / "stale",
                label="stale",
                status_class=".city-source-status--warning",
                timeout_ms=timeout_ms,
                exercise=False,
            )
        finally:
            stale.stop()

        await browser.close()

    (output / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New evidence directory. Existing metrics are never overwritten.",
    )
    parser.add_argument(
        "--channel",
        default="msedge",
        help="Installed Chromium channel. Pass an empty value for Playwright Chromium.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=180_000,
        help="State-based readiness timeout for cold ArcGIS and browser paths.",
    )
    args = parser.parse_args()
    result = asyncio.run(
        run(
            args.output.resolve(),
            args.channel or None,
            max(30_000, args.timeout_ms),
        )
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
