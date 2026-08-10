# Overview Context Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the opening Overview so FY2027 expenses and all funds are the default, revenue and expenses remain separate selectable measures, the chart selects fiscal year, and all KPI/caption values remain reconciled and accessible.

**Architecture:** Keep `OverviewSelectionState` as the single session state, but normalize Overview flow to `expense` or `revenue` and derive comparison year as `year - 1`. Put deterministic financial-summary logic in a small pure helper module, then have the existing Shiny Overview server render state from prepared rows/aggregates. Use semantic KPI buttons and a small JavaScript accessibility bridge for chart-year keyboard selection; scope all CSS to existing Overview/Story Studio selectors.

**Tech Stack:** Python 3.12, Shiny for Python 1.7, pandas 3, Plotly 6, pytest 9, Playwright, plain JavaScript, CSS.

## Global Constraints

- Present approved expenses and approved revenue estimates as separate measures; never add them into one dollar metric.
- Initial/reset state is exactly FY2027, Expenses, and All funds.
- The fixed benchmark is FY2027 all-funds expenses, derived from the prepared snapshot, with label `FY2027 Citywide Approved Expenses` and support `All funds approved spending plan | Not actual expenditures`.
- The analytical comparison year is exactly the immediately preceding numeric fiscal year; missing prior data is explicit and a zero prior value is described as new without a percentage.
- Full displayed dollar values use comma separators, never compact `M` or `B` notation.
- The top Revenue and Expenses cards are semantic buttons with keyboard operation, `aria-pressed`, visible focus, and selection not conveyed by color alone.
- The historical chart is the only year selector and has readable year labels, pointer and keyboard selection, persistent selected-year treatment, and an accessible `View FY#### details` cue.
- Keep the four-card desktop grid and established narrow stacking; prevent clipped values and horizontal overflow.
- Remove user-visible `movement` and `movements` contextually throughout the application.
- Keep protected navigation and footer markup, selectors, behavior, content, and styling unchanged.
- Do not change the prepared-cache/source-data contract or add dependencies.
- Do not use em dash characters in code comments, interface copy, or documentation.

---

### Task 1: Normalize Overview state and calculate separate measure summaries

**Files:**
- Create: `budget_app/ui/overview_metrics.py`
- Modify: `budget_app/state.py`
- Create: `tests/test_overview_metrics.py`
- Modify: `tests/test_state.py`

**Interfaces:**
- Produces: `OverviewMeasureSummary(year: int, prior_year: int, measure: str, current_amount: float, prior_amount: float | None, change_amount: float | None, change_percent: float | None, largest_department: str | None, largest_department_amount: float | None, largest_department_share: float | None)`.
- Produces: `build_overview_measure_summary(rows: pd.DataFrame, *, year: int, flow: Literal["revenue", "expense"], fund_scope: str) -> OverviewMeasureSummary`.
- Produces: `fixed_fy2027_expense_benchmark(rows: pd.DataFrame) -> float`.
- Produces: `format_signed_currency(value: float) -> str` and `format_signed_percent(value: float) -> str` for complete signed values.
- State contract: `sanitize_overview_selection()` selects FY2027 when present (otherwise latest), maps missing/legacy `all` flow to `expense`, preserves only `revenue`/`expense`, and always sets `compare_year = selected_year - 1`.

- [ ] **Step 1: Write failing state tests**

Add literal assertions in `tests/test_state.py` proving the empty/default selection is FY2027/2026/expense/all_funds, a selected FY2025 compares to FY2024 even if FY2024 is absent, and legacy flow `all` restores as `expense`.

- [ ] **Step 2: Run the state tests and verify RED**

Run: `uv run --isolated --python 3.12 pytest tests/test_state.py -q`

Expected: failures showing current defaults use latest/second-latest and `flow == "all"`.

- [ ] **Step 3: Implement minimal state normalization**

Update `sanitize_overview_selection()` so the selected year is bounded to available years, prefers 2027 only for a missing/invalid requested year, ignores independently restored comparison years, derives `selected_year - 1`, and normalizes `all` to `expense`. Retain `VALID_FLOWS` and legacy bookmark parsing because other restored URLs may still contain `all`.

- [ ] **Step 4: Run the state tests and verify GREEN**

Run: `uv run --isolated --python 3.12 pytest tests/test_state.py -q`

Expected: all state tests pass.

- [ ] **Step 5: Write failing summary tests**

Create a hand-built mixed-year, mixed-flow, mixed-fund-scope fixture and assert: revenue/expense are never combined; scope changes all outputs; prior is exactly `year - 1`; missing prior yields `None`; zero prior yields `change_percent is None`; largest department uses the active year/flow/scope and literal share; benchmark ignores active context and returns FY2027/all_funds/Expenses; signed formatters emit `+$84,321,004`, `-$2,000`, `+5.6%`, and `-1.2%`.

- [ ] **Step 6: Run summary tests and verify RED**

Run: `uv run --isolated --python 3.12 pytest tests/test_overview_metrics.py -q`

Expected: import failure because `budget_app.ui.overview_metrics` does not exist.

- [ ] **Step 7: Implement the pure summary module**

Use `filter_rows()` with `FLOW_VALUES = {"revenue": "Revenues", "expense": "Expenses"}`. Sum the active rows, query only `year - 1` for prior rows, return `None` for a missing prior group, suppress percentage when prior is zero, and group the active rows by department with deterministic amount-descending/name-ascending tie-breaking. Derive the benchmark from FY2027 expenses/all_funds rows.

- [ ] **Step 8: Run task tests and verify GREEN**

Run: `uv run --isolated --python 3.12 pytest tests/test_state.py tests/test_overview_metrics.py tests/test_data_domain.py -q`

Expected: all selected tests pass.

- [ ] **Step 9: Commit task files**

```powershell
git add budget_app/state.py budget_app/ui/overview_metrics.py tests/test_state.py tests/test_overview_metrics.py
git commit -m "feat: define overview measure summaries"
```

### Task 2: Rebuild Overview controls, KPIs, chart state, and terminology

**Files:**
- Modify: `budget_app/ui/story_studio.py`
- Modify: `budget_app/ui/modules/overview.py`
- Modify: `budget_app/ui/modules/what_changed.py`
- Modify: other `budget_app/**/*.py` only where a user-visible `movement` occurrence requires contextual `change` wording
- Modify: `tests/test_components.py`
- Modify: `tests/test_state.py` if bookmark expectations need the new derived comparison contract

**Interfaces:**
- Consumes: Task 1 summary and formatter functions.
- Produces: Shiny output `context_year` containing the active `FY####` header.
- Produces: top KPI buttons carrying `data-overview-measure="revenue|expense"` and `aria-pressed="true|false"` without `data-overview-select`, so measure selection does not open detail.
- Produces: chart-year selection requests through `overview-year_request` with payload `{year: number}`; the server updates year only and preserves measure/scope.
- Produces: reset button id `overview-reset` with accessible name/title `Reset to FY2027 expenses and all funds`.

- [ ] **Step 1: Write failing component/UI contract tests**

In `tests/test_components.py`, render the static Overview/Story Studio UI and assert absence of Fiscal Year, Compare With, Budget Flow, Active context, the duplicate disclaimer, and combined authority copy; assert presence of only Fund Scope, the icon reset accessible name, benchmark labels, four-card/chart output slots, and no user-visible `movement` wording in the rendered Overview composition.

- [ ] **Step 2: Run component tests and verify RED**

Run: `uv run --isolated --python 3.12 pytest tests/test_components.py -q`

Expected: failures on current controls/copy.

- [ ] **Step 3: Simplify static opening and control markup**

Update `story_studio_ui()` to accept the benchmark slot/value produced from the snapshot, show the fixed label and support copy once, and replace static live-year metadata with `ui.output_text("context_year")`. In `overview_ui()`, retain only Fund Scope plus a compact icon reset control; remove the active-filter output; change chart title/copy from movement to change.

- [ ] **Step 4: Rewire Overview selection state**

Remove effects for deleted `year`, `compare`, and `flow` inputs. Keep fund-scope synchronization. Add measure and year request effects that update only their state dimension, never open the detail drawer, and preserve hierarchy only where existing semantics remain valid. Reset to the Task 1 default. Ensure bookmark restore sanitizes legacy all-flow and independent comparison values.

- [ ] **Step 5: Render the four KPI cards from separate summaries**

Always calculate both top values for the active year/scope; use the selected measure summary for both lower cards and chart caption. Emit full currency, approved-estimate/spending-plan language, pressed state, `Viewing` text only inside the selected card if used, change/new/missing-prior copy, and largest-department amount/share. Remove Net Position and Budget Rows.

- [ ] **Step 6: Make the chart year-specific and explicit**

Plot only the selected measure and active scope; add x-axis `FY####` labels, pointer hover, persistent selected-year marker/border treatment, tooltip cue `View FY#### details`, and exact caption `FY####: $#,### | Change from FY####: +$#,### (+#.#%)`. For missing prior data render an explicit unavailable comparison; for prior zero render the signed amount plus `New in FY####` without a percentage.

- [ ] **Step 7: Complete the terminology review**

Search Python, JavaScript, and CSS-visible strings for `movement`/`movements`. Replace user-visible chart titles, captions, instructions, empty states, tooltips, section titles, and accessible names contextually with `change`/`changes`; leave internal identifiers when renaming adds migration risk.

- [ ] **Step 8: Run task tests and verify GREEN**

Run: `uv run --isolated --python 3.12 pytest tests/test_components.py tests/test_state.py tests/test_overview_metrics.py -q`

Expected: all selected tests pass.

- [ ] **Step 9: Commit task files**

```powershell
git add budget_app/ui/story_studio.py budget_app/ui/modules/overview.py budget_app/ui/modules/what_changed.py tests/test_components.py tests/test_state.py
git add -u budget_app www
git commit -m "feat: simplify overview analytical context"
```

### Task 3: Add keyboard chart selection, responsive styling, and browser coverage

**Files:**
- Modify: `www/app.js`
- Modify: `www/city.css`
- Modify: `budget_app/application.py`
- Modify: `tests/e2e/test_app.py`
- Modify: `tests/e2e/conftest.py` only if required for deterministic viewport coverage

**Interfaces:**
- Consumes: Task 2 `data-overview-measure`, `overview-year_request`, reset id/name, KPI and chart markup.
- Produces: delegated click/Enter/Space handling for measure cards and keyboard-equivalent year controls without triggering the detail drawer.
- Produces: visible `:focus-visible`, hover, pressed/selected, and tooltip states scoped to the Overview.

- [ ] **Step 1: Write failing Playwright tests**

Update obsolete reset/bookmark expectations and add one focused Overview contract covering: no deleted controls; exact fixed benchmark; default expense card pressed; mouse plus Enter/Space measure selection; no drawer opening; selected year by chart pointer and keyboard equivalent; live year, top/lower KPIs, caption, and scope all update; reset restores FY2027/expense/all_funds; exact reset accessible name; no visible movement wording; full dollar values; and no horizontal overflow at 2048, 1440, and 800 CSS pixels.

- [ ] **Step 2: Run the focused browser tests and verify RED**

Run: `uv run --isolated --python 3.12 pytest -m e2e tests/e2e/test_app.py -q -k "overview"`

Expected: failures on missing selectors/interactions and old markup.

- [ ] **Step 3: Add the client interaction bridge**

In `www/app.js`, add separate delegated handlers for measure cards and semantic year controls. Send Shiny inputs with event priority, update immediate pressed/selected state only within the relevant control group, support Enter and Space, and leave existing `[data-overview-select]` detail behavior unchanged for department/fund drilldown controls.

- [ ] **Step 4: Update scoped Story Studio/Overview CSS**

Rework only `.city-story-studio__*`, `.city-overview-*`, and new Overview selector rules. Keep the two-by-two desktop KPI grid, increase card height/padding/label prominence, make full values wrap safely, style pressed cards with border/background plus non-color indicator, give reset and year controls visible hover/focus/tooltip treatment, close removed-control whitespace, and preserve established narrow stacking. Do not alter any `.city-header*`, `.portal-link*`, `.city-brand*`, `.city-nav*`, `.city-mobile-nav*`, `.city-resources*`, `.city-footer*`, or `.city-footer-logo` rules.

- [ ] **Step 5: Bump the stylesheet cache key**

Update only the `city.css?v=` query string in `budget_app/application.py` after CSS changes.

- [ ] **Step 6: Run focused browser tests and verify GREEN**

Run: `uv run --isolated --python 3.12 pytest -m e2e tests/e2e/test_app.py -q -k "overview"`

Expected: all focused Overview browser tests pass with no page or console errors.

- [ ] **Step 7: Run visual verification at required widths**

Launch the app with `SHINY_TESTMODE=1` and Playwright. Capture/inspect 2048, 1440, and 800 CSS-pixel screenshots. At each width verify no horizontal overflow/clipping, readable full values, the expected card grid/stack order, visible selected/focus states, and unchanged header/footer geometry and copy.

- [ ] **Step 8: Run full verification**

Run:

```powershell
uv run --isolated --python 3.12 pytest -q -m "not live"
uv run --isolated --python 3.12 ruff check .
uv run --isolated --python 3.12 ruff format --check .
```

Expected: all non-live tests pass; Ruff lint and format checks exit zero.

- [ ] **Step 9: Commit task files**

```powershell
git add www/app.js www/city.css budget_app/application.py tests/e2e/test_app.py tests/e2e/conftest.py
git commit -m "test: verify accessible overview interactions"
```
