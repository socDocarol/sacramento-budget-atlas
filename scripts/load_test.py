"""Run the warm-snapshot, multi-session pilot browser check."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


async def open_session(browser: Browser, url: str, ready_timeout_ms: int) -> tuple[BrowserContext, Page]:
    context = await browser.new_context()
    page = await context.new_page()
    response = await page.goto(url, wait_until="domcontentloaded")
    if response is None or not response.ok:
        await context.close()
        status = response.status if response is not None else "no response"
        raise RuntimeError(f"Application navigation failed with status {status}")
    await page.locator(".city-source-status--fresh").wait_for(
        state="visible",
        timeout=ready_timeout_ms,
    )
    return context, page


async def run(url: str, sessions: int, channel: str | None, ready_timeout_ms: int) -> dict[str, Any]:
    async with async_playwright() as playwright:
        launch_options: dict[str, Any] = {"headless": True}
        if channel:
            launch_options["channel"] = channel
        browser = await playwright.chromium.launch(**launch_options)
        opened: list[tuple[BrowserContext, Page]] = []
        failures: list[str] = []
        isolated = False
        try:
            results = await asyncio.gather(
                *(open_session(browser, url, ready_timeout_ms) for _ in range(sessions)),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    failures.append(str(result))
                else:
                    opened.append(result)

            if len(opened) == sessions:
                first_page = opened[0][1]
                await first_page.locator("#overview-flow").select_option("expense")
                if await first_page.locator("#overview-flow").input_value() != "expense":
                    raise RuntimeError("The first session did not accept its input change")
                await asyncio.sleep(0.5)
                other_values = await asyncio.gather(
                    *(page.locator("#overview-flow").input_value() for _, page in opened[1:])
                )
                isolated = all(value == "all" for value in other_values)
        finally:
            await asyncio.gather(
                *(context.close() for context, _ in opened),
                return_exceptions=True,
            )
            await browser.close()

    return {
        "requested_sessions": sessions,
        "ready_timeout_ms": ready_timeout_ms,
        "ready_sessions": len(opened),
        "failures": failures,
        "session_state_isolated": isolated,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/")
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument(
        "--channel",
        default="msedge",
        help="Installed Chromium channel. Pass an empty value for Playwright Chromium.",
    )
    parser.add_argument(
        "--ready-timeout-ms",
        type=int,
        default=30_000,
        help="Per-session wait limit for the fresh source status.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON artifact destination for the session-isolation result.",
    )
    args = parser.parse_args()
    result = asyncio.run(
        run(
            args.url,
            max(1, args.sessions),
            args.channel or None,
            max(1_000, args.ready_timeout_ms),
        )
    )
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["ready_sessions"] != result["requested_sessions"]:
        raise SystemExit(1)
    if result["failures"] or not result["session_state_isolated"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
