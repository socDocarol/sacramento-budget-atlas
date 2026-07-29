"""Repeat the rapid drawer lifecycle contract in isolated browser sessions."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_EXPRESSION = "rapid_open_close_open_and_repeated_cycles_leave_one_clean_shell"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop after the first nonzero test result.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Write lifecycle and focus trace JSON for each exercised run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/ui-audit/drilldown-follow-up/rapid-cycle-repetitions"),
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    temporary_root = PROJECT_ROOT / "artifacts" / "e2e-temp" / f"rc-{time.time_ns():x}"
    results: list[dict[str, object]] = []

    for index in range(1, max(1, args.repetitions) + 1):
        run_root = output / f"run-{index:02d}"
        run_root.mkdir(parents=True, exist_ok=True)
        short_temp_root = temporary_root / f"run-{index:02d}"
        runtime_temp = short_temp_root / "runtime"
        pytest_temp = short_temp_root / "pytest"
        runtime_temp.mkdir(parents=True, exist_ok=True)
        environment = {
            **os.environ,
            "BUDGET_E2E_URL": args.url,
            "TEMP": str(runtime_temp),
            "TMP": str(runtime_temp),
            "TMPDIR": str(runtime_temp),
        }
        trace_path = run_root / "rapid-cycle-trace.json"
        if args.trace:
            environment["BUDGET_RAPID_CYCLE_TRACE_PATH"] = str(trace_path)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "e2e",
            "-k",
            TEST_EXPRESSION,
            "-vv",
            "--basetemp",
            str(pytest_temp),
        ]
        started = time.monotonic()
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        log_path = run_root / "pytest.stdout.log"
        log_path.write_text(completed.stdout, encoding="utf-8")
        results.append(
            {
                "run": index,
                "returnCode": completed.returncode,
                "durationMs": duration_ms,
                "log": str(log_path),
                "trace": str(trace_path) if args.trace else None,
            }
        )
        if completed.returncode and args.stop_on_failure:
            break

    summary = {
        "target": args.url,
        "testExpression": TEST_EXPRESSION,
        "requestedRepetitions": max(1, args.repetitions),
        "temporaryRoot": str(temporary_root),
        "stopOnFailure": args.stop_on_failure,
        "traceEnabled": args.trace,
        "results": results,
        "allPassed": all(result["returnCode"] == 0 for result in results),
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["allPassed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
