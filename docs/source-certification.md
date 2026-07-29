# Source certification

Date: July 29, 2026

## Certified application base

The source base is the non-Git workspace folder `budget-shiny-python`. It was
copied as source into `sacramento-budget-atlas` after bounded verification.
The source lockfile SHA-256 is
`B8D432CB0FA1B4F7202AB4030B4F32DDE9E50958D89AE46C0697C63839942D28`.

Verified properties:

- Python 3.12 and Shiny for Python 1.7.0 are locked.
- The prepared bundle pointer is `v1-d3894619890346c9`.
- The bundle contains normalized rows, choices, hierarchy, totals, indexes,
  and chart-ready aggregates.
- Atomic promotion, active and prior fallback, immutable process sharing,
  single-flight refresh, stale behavior, lazy views, and deterministic test
  facilities remain in the copied code.
- The standalone copy preserves the prepared bundle and has its own `.venv`,
  cache path, artifacts, and server port.

Verification:

```text
uv run ruff check --no-cache .
Result: passed

uv run pytest -p no:cacheprovider tests/test_prepared_bundle.py
  tests/test_snapshot_store.py tests/test_data_repository.py
  tests/test_components.py tests/test_assets.py
Result: 14 passed, 1 dependency deprecation warning
```

Runtime-only directories and historical evidence were excluded from the copy:
the source `.venv`, bytecode, `.pytest_cache`, `.ruff_cache`, `debug.log`, and
the source `artifacts` directory.

## Certified platform

`city-shiny-platform` is a source-only reusable package workspace. Its package
boundary check passed and its complete documented source-only suite passed:
43 tests.

The platform packages remain read-only. The Atlas uses their documented
contracts as architectural boundaries, while retaining the richer
Budget-specific prepared bundle in the application. Copying platform package
source into this rapid demo would add integration risk without improving the
meeting path.

## Source decision

`budget-shiny-python` is the effective application base.
`city-shiny-platform` is the validated contract reference.
`fancy-budget-shiny-python` is not an implementation source.

The source projects are non-Git folders. Their pre-build SHA-256 manifests
were compared after implementation:

- `budget-shiny-python`: 102 entries checked, 0 changed or missing
- `city-shiny-platform`: 49 entries checked, 0 changed or missing
- `fancy-budget-shiny-python`: 110 entries checked, 0 changed or missing

The demo copy's `budget_app/ui/shell.py` and `www/app.js` are byte-for-byte
identical to the certified Budget source. The Story Studio is inserted only
inside the copied Overview panel.
