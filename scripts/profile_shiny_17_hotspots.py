"""Profile deterministic Budget data and Overview hot paths from a saved cache."""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from budget_app.data.domain import build_snapshot  # noqa: E402
from budget_app.data.normalize import normalize_frame  # noqa: E402
from budget_app.state import sanitize_overview_selection  # noqa: E402
from budget_app.ui.modules.overview import _state_rows  # noqa: E402


def _timed(name: str, operation: Any, repetitions: int) -> dict[str, Any]:
    samples: list[float] = []
    result: Any = None
    for _ in range(repetitions):
        started = time.perf_counter()
        result = operation()
        samples.append((time.perf_counter() - started) * 1000)
    return {
        "name": name,
        "repetitions": repetitions,
        "minimum_ms": round(min(samples), 3),
        "median_ms": round(sorted(samples)[len(samples) // 2], 3),
        "maximum_ms": round(max(samples), 3),
        "result_rows": len(result) if hasattr(result, "__len__") else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    parquet_path = args.cache_dir.resolve() / "approved-budgets.parquet"
    output_dir = args.output.resolve()
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing profile directory: {output_dir}")
    output_dir.mkdir(parents=True)

    raw = pd.read_parquet(parquet_path)
    normalized = normalize_frame(raw)
    snapshot = build_snapshot(normalized, source_url="profile://saved-cache")
    years = tuple(int(value) for value in snapshot.years)
    state = sanitize_overview_selection(
        None,
        years=years,
        departments=tuple(normalized["department"].dropna().astype(str).unique()),
        funds=tuple(normalized["fund"].dropna().astype(str).unique()),
        categories=tuple(normalized["category"].dropna().astype(str).unique()),
        records=tuple(normalized["object_id"].dropna().astype(int).unique()),
    )

    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(25):
        normalize_frame(raw)
        build_snapshot(normalized, source_url="profile://saved-cache")
        sanitize_overview_selection(
            state,
            years=years,
            departments=tuple(normalized["department"].dropna().astype(str).unique()),
            funds=tuple(normalized["fund"].dropna().astype(str).unique()),
            categories=tuple(normalized["category"].dropna().astype(str).unique()),
            records=tuple(normalized["object_id"].dropna().astype(int).unique()),
        )
        _state_rows(normalized, state, year=state.year)
        _state_rows(normalized, state, year=state.compare_year)
        _state_rows(normalized, state, year=None)
    profiler.disable()

    profile_path = output_dir / "hotspots.prof"
    profiler.dump_stats(profile_path)
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative")
    stats.print_stats(40)
    (output_dir / "hotspots.txt").write_text(stream.getvalue(), encoding="utf-8")

    metrics = {
        "cache_parquet": str(parquet_path),
        "source_rows": len(normalized),
        "years": list(years),
        "timers": [
            _timed("parquet_read", lambda: pd.read_parquet(parquet_path), 7),
            _timed("normalize_frame", lambda: normalize_frame(raw), 25),
            _timed(
                "build_snapshot",
                lambda: build_snapshot(normalized, source_url="profile://saved-cache"),
                25,
            ),
            _timed("overview_current_rows", lambda: _state_rows(normalized, state, year=state.year), 50),
            _timed(
                "overview_comparison_rows",
                lambda: _state_rows(normalized, state, year=state.compare_year),
                50,
            ),
            _timed("overview_history_rows", lambda: _state_rows(normalized, state, year=None), 50),
        ],
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
