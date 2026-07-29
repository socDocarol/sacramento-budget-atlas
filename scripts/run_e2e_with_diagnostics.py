"""Run the full browser suite with a durable active-test diagnostic artifact."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
URL_WITH_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s'\"]+")
ACTIVE_TEST = re.compile(r"E2E_ACTIVE_TEST\s+([^\r\n]+)")


def safe_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def redact_url_query(line: str) -> str:
    return URL_WITH_QUERY.sub(r"\1?<redacted>", line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/ui-audit/drilldown-follow-up/e2e-diagnostics"),
    )
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    pytest_temp = args.output / "pytest-temp"
    runtime_temp = args.output / "runtime-temp"
    runtime_temp.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "e2e",
        "-vv",
        "-s",
        "--basetemp",
        str(pytest_temp),
        "--durations=25",
    ]
    environment = {
        **os.environ,
        "BUDGET_E2E_URL": args.url,
        "BUDGET_E2E_DIAGNOSTICS": "1",
        "PYTHONUNBUFFERED": "1",
        "TEMP": str(runtime_temp),
        "TMP": str(runtime_temp),
        "TMPDIR": str(runtime_temp),
    }
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    current_test: str | None = None
    timed_out = False
    start = time.monotonic()
    log_path = args.output / "full-e2e.stdout.log"
    with log_path.open("w", encoding="utf-8", newline="") as log:
        while True:
            if time.monotonic() - start > args.timeout_seconds:
                timed_out = True
                break
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            if line is None:
                break
            safe_line = redact_url_query(line)
            log.write(safe_line)
            print(safe_line, end="")
            active_match = ACTIVE_TEST.search(safe_line)
            if active_match:
                current_test = active_match.group(1).strip()

    if timed_out and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    return_code = process.wait(timeout=10)
    summary = {
        "target": safe_url(args.url),
        "command": command,
        "timeoutSeconds": args.timeout_seconds,
        "timedOut": timed_out,
        "activeTestAtStop": current_test,
        "returnCode": return_code,
        "log": str(log_path),
    }
    summary_path = args.output / "full-e2e.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if timed_out:
        raise SystemExit(f"Full E2E suite timed out while running: {current_test or 'unknown test'}")
    if return_code:
        raise SystemExit(return_code)


if __name__ == "__main__":
    main()
