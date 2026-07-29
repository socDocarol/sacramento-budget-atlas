# Pilot Validation Report

## Live source snapshot

- Source: City of Sacramento Approved Budgets FeatureServer layer 0
- Rows: 29,387
- Fiscal years: FY2013 through FY2027
- Latest fiscal year: FY2027, discovered from the source
- Duplicate ObjectIds: 0
- Unknown fund scopes: 0
- Revenue reconciliation delta: 0
- Expense reconciliation delta: 0

## Product acceptance evidence

- Four primary analysis views and two grouped resource views render through the
  custom City shell. Drilldown is no longer a top-level destination.
- Overview totals, movements, chart marks, and supporting rows open synchronized
  quick detail without changing views. Desktop uses a drawer and mobile uses a
  viewport-capped bottom sheet.
- Quick detail expands into a department, fund, and category workspace inside
  Overview, with breadcrumbs, back, clear, collapse, exact records, and linked
  charts.
- Navigation has one state authority. Repeated navigation, rapid navigation,
  browser history, refresh, unknown hashes, and legacy Drilldown URLs are
  covered by browser tests.
- Department, fund, category, selected-record, drawer, workspace, filters, and
  comparison state can be bookmarked and reopened in another session.
- A representative deep bookmark was 1,201 characters. The browser regression
  requires restored URLs to remain below 2,048 characters and excludes DataGrid
  transport state.
- Explorer selections update the full-width comparison chart and exact detail.
  Active filters, reset, export, and copy-state actions are present.
- Scenario validation prevents negative allocations and enforces balanced mode.
- A no-snapshot source failure produces a full retry state.
- Exactly one main landmark and a working skip link are present.
- The final capture contract produced 36 screenshots in
  `artifacts/ui-audit/after/`: six final views at 390, 768, 1024, and 1440
  pixels, plus department, fund, and category detail at each width.
- The capture contract found no browser-console errors, duplicate authored IDs,
  unnamed visible controls, missing image alternatives, inaccessible dialogs,
  clipped controls, page-level horizontal overflow, missing primary headings,
  or Explorer mobile chart-geometry failures.
- Direct visual inspection covered every view plus department, fund, and
  category detail at all four widths. Representative mobile, tablet, and
  desktop layouts were accepted after screenshot-driven correction.

## Automated validation

- Non-browser suite: 23 passed.
- Browser suite: 19 passed. The JUnit result is
  `artifacts/ui-audit/pytest-e2e-final4.xml`; console output is
  `artifacts/ui-audit/pytest-e2e-final4.stdout.log`.
- Live ArcGIS contract: 1 passed.
- Ten simultaneous warm browser sessions: 10 ready, 0 failures, session state
  isolated.
- Static analysis: `ruff check` passed.
- Formatting: all 37 Python files passed `ruff format --check`.
- JavaScript syntax: `node --check www/app.js` passed.
- Python compilation: `compileall` passed without warnings.

## Runtime and operational validation

- The dependency graph resolves from the frozen `uv.lock`.
- The application imports under Python 3.12.
- Static analysis, formatting, unit, contract, live, and browser test commands
  are documented in the project README.
- The final local process is healthy at `http://127.0.0.1:8000/`.
- Final server logs recorded 44 fresh snapshot-ready sessions with 29,387 rows
  and FY2027 as the latest year. No `budget_app` error, traceback, nonfinite
  serialization error, or non-transport warning was present.
- Windows asyncio logged connection-reset and `socket.send()` messages after
  automated Playwright contexts deliberately closed their WebSockets. These
  transport-close messages did not interrupt a session, fail a capture, alter
  the 10-session result, or make the health endpoint unavailable.
- The Linux Python 3.12 slim container configuration selects a non-root user
  and declares a read-only application filesystem with a writable cache mount.
- A local container build was not executed because this workstation has no
  Docker or Podman engine installed.
- No deployment, push, pull request, or external-system change was performed.

## Approval boundary

These checks establish technical pilot readiness only. Complete
[the data-owner review](data-owner-review.md) before leadership use.
