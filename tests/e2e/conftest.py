from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.request import urlopen

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAPID_CYCLE_TEST = "rapid_open_close_open_and_repeated_cycles_leave_one_clean_shell"


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int | None, str]) -> None:
    """Make a stalled full-E2E invocation identify its active test in the log."""
    if os.getenv("BUDGET_E2E_DIAGNOSTICS") == "1":
        print(f"E2E_ACTIVE_TEST {nodeid}", flush=True)


@pytest.fixture(autouse=True)
def rapid_cycle_trace(request: pytest.FixtureRequest) -> Iterator[None]:
    """Persist opt-in focus/lifecycle evidence for one rapid-cycle browser run."""
    trace_path = os.getenv("BUDGET_RAPID_CYCLE_TRACE_PATH")
    if not trace_path or RAPID_CYCLE_TEST not in request.node.nodeid:
        yield
        return

    page = request.getfixturevalue("page")
    page.add_init_script(
        """() => {
          const trace = window.__rapidCycleTrace = { events: [], descriptor: null };
          const describe = node => {
            if (!node) return null;
            const selection = Object.fromEntries(Array.from(node.attributes || [])
              .filter(attribute => attribute.name.startsWith('data-selection-'))
              .map(attribute => [attribute.name, attribute.value]));
            return {
              tag: node.tagName.toLowerCase(), id: node.id || null,
              className: typeof node.className === 'string' ? node.className : null,
              selection, ariaHidden: node.getAttribute?.('aria-hidden') || null,
              inert: Boolean(node.closest?.('[inert]'))
            };
          };
          const visible = node => {
            if (!node || node.closest('[hidden], [aria-hidden="true"]')) return false;
            const style = getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          };
          const snapshot = reason => {
            const overlay = document.querySelector('[data-detail-overlay]');
            const drawer = overlay && overlay.querySelector('.city-detail-drawer');
            const candidates = trace.descriptor ? Array.from(document.querySelectorAll('[data-overview-select]'))
              .filter(node => Object.entries(trace.descriptor).every(([name, value]) => node.getAttribute(name) === value)) : [];
            trace.events.push({
              at: Number(performance.now().toFixed(2)), reason,
              active: describe(document.activeElement),
              lifecycle: overlay?.getAttribute('data-detail-lifecycle') || null,
              shell: overlay ? {
                ariaHidden: overlay.getAttribute('aria-hidden'),
                contentState: overlay.getAttribute('data-detail-content-state'),
                drawerAriaHidden: drawer?.getAttribute('aria-hidden') || null,
                title: drawer?.querySelector('.city-detail-drawer__title')?.textContent?.trim() || null
              } : null,
              matchingCandidates: {
                count: candidates.length,
                visible: candidates.filter(visible).length,
                inert: candidates.filter(node => Boolean(node.closest('[inert]'))).length
              }
            });
          };
          document.addEventListener('pointerdown', event => {
            const trigger = event.target.closest?.('[data-overview-select]');
            if (trigger) {
              trace.descriptor = Object.fromEntries(Array.from(trigger.attributes)
                .filter(attribute => attribute.name.startsWith('data-selection-'))
                .map(attribute => [attribute.name, attribute.value]));
              snapshot('pointerdown:overview-trigger');
            }
          }, true);
          document.addEventListener('focusin', event => snapshot('focusin:' + (event.target.id || event.target.tagName.toLowerCase())), true);
          document.addEventListener('budget:detail-lifecycle', event => {
            const lifecycle = event.detail?.lifecycle || 'unknown';
            snapshot('lifecycle:' + lifecycle);
            if (lifecycle === 'closed') [0, 50, 200, 700, 1500].forEach(delay => {
              setTimeout(() => snapshot('closed+' + delay + 'ms'), delay);
            });
          });
        }"""
    )
    yield
    try:
        trace = page.evaluate("() => window.__rapidCycleTrace || null")
        if trace is not None:
            destination = Path(trace_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    except Exception as error:  # pragma: no cover - diagnostic teardown must not hide the test result
        print(f"RAPID_CYCLE_TRACE_WRITE_FAILED {error}", flush=True)


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="session")
def browser_type_launch_args() -> dict[str, object]:
    return {"channel": "msedge", "headless": True}


@pytest.fixture(scope="session")
def live_server_url() -> Iterator[str]:
    configured = os.getenv("BUDGET_E2E_URL")
    if configured:
        yield configured.rstrip("/")
        return

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    command = [
        sys.executable,
        "-m",
        "shiny",
        "run",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "app.py",
    ]
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "BUDGET_CACHE_DIR": str(PROJECT_ROOT / ".cache"),
            "BUDGET_BACKGROUND_REFRESH_ENABLED": "0",
            "SHINY_TESTMODE": "1",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The Shiny test server exited before becoming ready")
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("The Shiny test server did not become ready")

    yield url
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture()
def error_server_url(tmp_path: Path) -> Iterator[str]:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "shiny",
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "app.py",
        ],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "BUDGET_ARCGIS_URL": "http://127.0.0.1:9/unavailable/FeatureServer/0",
            "BUDGET_CACHE_DIR": str(tmp_path),
            "BUDGET_BACKGROUND_REFRESH_ENABLED": "1",
            "SHINY_TESTMODE": "1",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("The error-state Shiny server did not become ready")

    yield url
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture()
def stale_server_url(tmp_path: Path) -> Iterator[str]:
    source_cache = PROJECT_ROOT / ".cache"
    for name in ("approved-budgets.parquet", "approved-budgets.metadata.json"):
        shutil.copy2(source_cache / name, tmp_path / name)

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    shiny = Path(sys.executable).with_name("shiny.exe")
    process = subprocess.Popen(  # noqa: S603
        [
            str(shiny),
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "app.py",
        ],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "BUDGET_ARCGIS_URL": "http://127.0.0.1:9/unavailable/FeatureServer/0",
            "BUDGET_CACHE_DIR": str(tmp_path),
            "BUDGET_CACHE_TTL_SECONDS": "1",
            "BUDGET_BACKGROUND_REFRESH_ENABLED": "1",
            "SHINY_TESTMODE": "1",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The stale-state Shiny server exited before becoming ready")
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("The stale-state Shiny server did not become ready")

    yield url
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture()
def production_mode_server_url() -> Iterator[str]:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    shiny = Path(sys.executable).with_name("shiny.exe")
    production_env = dict(os.environ)
    production_env.pop("SHINY_TESTMODE", None)
    production_env["BUDGET_CACHE_DIR"] = str(PROJECT_ROOT / ".cache")
    production_env["BUDGET_BACKGROUND_REFRESH_ENABLED"] = "0"
    process = subprocess.Popen(  # noqa: S603
        [
            str(shiny),
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "app.py",
        ],
        cwd=PROJECT_ROOT,
        env=production_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The production-mode Shiny server exited before becoming ready")
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("The production-mode Shiny server did not become ready")

    yield url
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
