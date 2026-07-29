"""Measure prepared-bundle startup without contacting the production source."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from pathlib import Path

from playwright.async_api import async_playwright
from run_shiny_17_performance_audit import (
    DEFAULT_STALE_URL,
    PROJECT_ROOT,
    LocalServer,
    measure_page,
    ten_session_memory,
)


def copy_prepared_cache(source: Path, target: Path) -> None:
    if not (source / "current.json").is_file():
        raise RuntimeError(f"No prepared current.json found in {source}")
    shutil.copytree(source, target)


async def run(output: Path, source_cache: Path, channel: str | None, timeout_ms: int) -> dict:
    metrics_path = output / "metrics.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite evidence directory: {output}")
    output.mkdir(parents=True)
    cache_dir = output / "cache"
    copy_prepared_cache(source_cache, cache_dir)
    launch_options = {"headless": True}
    if channel:
        launch_options["channel"] = channel
    result: dict = {
        "deterministic_prepared_cache": True,
        "source_cache": str(source_cache),
        "network_source_disabled": True,
    }
    disabled_refresh = {
        "BUDGET_BACKGROUND_REFRESH_ENABLED": "0",
        "BUDGET_ARCGIS_URL": DEFAULT_STALE_URL,
    }

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**launch_options)
        warm = LocalServer("prepared-warm", output / "prepared-warm", cache_dir, disabled_refresh)
        try:
            warm.start(timeout_seconds=max(45, timeout_ms / 1000))
            result["warm_http_ready_ms"] = warm.http_ready_ms
            result["warm_memory_before_session"] = warm.memory()
            result["warm_first"] = await measure_page(
                browser,
                warm,
                output / "prepared-warm",
                label="prepared-warm-first",
                status_class=".city-source-status--fresh",
                timeout_ms=timeout_ms,
                exercise=True,
            )
            result["warm_in_process"] = await measure_page(
                browser,
                warm,
                output / "prepared-warm",
                label="prepared-warm-in-process",
                status_class=".city-source-status--fresh",
                timeout_ms=timeout_ms,
                exercise=False,
            )
            result["ten_sessions"] = await ten_session_memory(browser, warm, timeout_ms)
        finally:
            warm.stop()

        restart = LocalServer("prepared-restart", output / "prepared-restart", cache_dir, disabled_refresh)
        try:
            restart.start(timeout_seconds=max(45, timeout_ms / 1000))
            result["restart_http_ready_ms"] = restart.http_ready_ms
            result["warm_restart"] = await measure_page(
                browser,
                restart,
                output / "prepared-restart",
                label="prepared-warm-restart",
                status_class=".city-source-status--fresh",
                timeout_ms=timeout_ms,
                exercise=True,
            )
        finally:
            restart.stop()
        await browser.close()

    metrics_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path, default=PROJECT_ROOT / ".cache")
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--timeout-ms", type=int, default=120_000)
    args = parser.parse_args()
    result = asyncio.run(
        run(
            args.output.resolve(),
            args.source_cache.resolve(),
            args.channel or None,
            max(30_000, args.timeout_ms),
        )
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
