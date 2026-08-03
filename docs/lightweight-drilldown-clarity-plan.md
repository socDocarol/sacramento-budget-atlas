# Lightweight Drilldown Clarity Plan

**Status:** Plan only. No drilldown implementation is included in this branch.

**Baseline:** `main` at merge commit `d554d49`, which contains the accepted
opening-layout refinement from pull request 1.

## Outcome

Make every integrated Overview drilldown clearly identify the selected fiscal
year, flow, fund scope, hierarchy level, and record context while preserving the
existing fast, persistent drawer on desktop and bottom sheet on smaller screens.

The implementation should improve orientation and semantic accuracy without
adding another route, another drawer, another Plotly instance, or another source
request.

## Problem statement

The current selection system already applies meaningful analytical filters:

- Fiscal-year chart bars update the selected year.
- Revenue and expense cards update the selected flow.
- Fund-scope cards update the selected scope.
- Department, fund, and category interactions refine the hierarchy.
- Exact-row interactions carry the selected ObjectId.

The drawer content changes with those filters, but the heading usually falls
back to `Citywide budget detail`, the breadcrumb can remain only `Citywide`, and
several section labels use generic `approved amount` wording. The user therefore
has to infer which context is active from changed values.

Two homepage cards have an additional semantic mismatch:

- Net Position opens the combined revenue-plus-expense authority view instead
  of leading with the displayed revenue-less-expenses value.
- Budget Rows opens a currency-led view instead of leading with the displayed
  record count.

## Product decision

Use one shared persistent drawer with two kinds of state:

1. `OverviewSelectionState` remains the sole analytical filter authority.
2. A small presentation lens distinguishes views that cannot be inferred from
   the analytical filters alone.

The supported presentation lenses should be:

- `authority`, the default for revenue, expenses, combined authority, years,
  fund scopes, departments, funds, categories, and exact records.
- `net_position`, used only when Net Position is the selected entry point.
- `source_records`, used only when Budget Rows is the selected entry point.

The presentation lens must not alter source rows or filter calculations. It may
select labels, summary formulas, trend measures, focus targets, and accent
treatment.

## Expected behavior matrix

| Entry point | Analytical context | Presentation lens | Required drawer identity |
| --- | --- | --- | --- |
| Approved Revenue | FY2027, revenue, all funds | `authority` | `Citywide approved revenue`, with FY2027 and all-funds context |
| Approved Expenses | FY2027, expenses, all funds | `authority` | `Citywide approved expenses`, with FY2027 and all-funds context |
| Net Position | FY2027, revenue and expenses, all funds | `net_position` | `Citywide net position`, leading with revenue less expenses |
| Budget Rows | FY2027, revenue and expenses, all funds | `source_records` | `FY2027 approved-budget source records`, leading with matching rows |
| General Fund scope | FY2027, expenses, General Fund scope | `authority` | `General Fund approved expenses`, with amount, share, and row count |
| Other fund scope | FY2027, expenses, selected scope | `authority` | Selected scope name plus approved-expense context |
| Fiscal-year chart bar | Selected year and current flow/scope | `authority` | Selected fiscal year, flow, and scope in the heading and context line |
| Department | Selected department and current filters | `authority` | Department name plus flow, fiscal year, and scope |
| Fund | Selected department and fund | `authority` | Fund name plus its department path and current filters |
| Category | Selected department, fund, and category | `authority` | Category name plus the full hierarchy path |
| Exact record | Current hierarchy plus ObjectId | `authority` | ObjectId plus its fiscal year, flow, and hierarchy |

## Presentation model

Create one pure, inexpensive presentation mapper from the sanitized selection
and presentation lens. It should return display values such as:

- Eyebrow, for example `APPROVED EXPENSES · FY2027`.
- Title, for example `General Fund`.
- Context summary, for example `$732.2M · 4,942 records`.
- Breadcrumb, for example `Citywide / General Fund`.
- Accent token, using the existing revenue, expense, net, and record colors.
- Current and comparison metric labels.
- Trend and exact-table labels.
- Expand-analysis target.

The mapper must be deterministic, free of reactive reads, and independently
unit tested. Reactive code should read current state once and pass ordinary
values into it.

### Title priority

Use the deepest available context as the visible title:

1. ObjectId
2. Category
3. Fund
4. Department
5. Non-default fund scope
6. Citywide context

Flow and fiscal year should remain visible in the eyebrow or context line even
when the title is a department, fund, category, or record.

## State and bookmark boundary

Keep year, comparison year, flow, scope, department, fund, category, and
selected record in `OverviewSelectionState`.

Add the bounded presentation lens to `OverviewPresentationState`, alongside
the existing drawer and workspace flags. Sanitize unknown values back to
`authority`.

Include the lens in copied and restored state so a shared Net Position or
Budget Rows drawer restores with the same meaning. Legacy bookmarks without a
lens must continue to restore as `authority`.

Every new selection trigger must explicitly resolve a lens. A scope, year,
department, fund, category, or record click must reset a previously selected
Net Position or Budget Rows lens to `authority` rather than accidentally
carrying it forward.

## Drawer header

Retain the current drawer element, dialog semantics, lifecycle, and focus
behavior. Replace generic identity with state-derived text:

```text
FUND SCOPE · APPROVED EXPENSES
General Fund
FY2027 · $732.2M · 4,942 records
Citywide / General Fund
```

Header requirements:

- The title must identify the selected entity or metric without relying on
  color.
- Fiscal year and flow must remain visible at every hierarchy level.
- Breadcrumbs must show the selected path and wrap naturally.
- The existing accent colors may appear as a narrow rule or eyebrow treatment.
- Screen readers must continue to receive the dynamic title through
  `aria-labelledby`.
- Loading behavior must never expose a stale title from the previous context.

The current lifecycle already compares the rendered title with the expected
title before marking detail ready. Preserve that stale-content protection.
Measure title latency before adding client-side presentation duplication. If
the current server title reaches the drawer within the agreed budget, keep the
mapping server-side.

## Context-sensitive summary metrics

### Authority lens

- Revenue flow: lead with approved revenue.
- Expense flow: lead with approved expenses.
- Combined flow: label the sum as combined approved authority rather than a
  generic current total.
- Current and comparison values use the selected hierarchy and scope.
- Historical labels name the active flow or combined authority explicitly.

### Net Position lens

- Lead with current revenue less current expenses.
- Show current approved revenue and current approved expenses as supporting
  values.
- Comparison and change use the same net formula for the comparison year.
- Reuse the existing trend surface to show annual net position rather than
  adding a second chart.
- Exact supporting records remain available because both flows are required to
  substantiate the calculation.

### Source Records lens

- Lead with matching current-year row count.
- Show revenue-row and expense-row counts as supporting values.
- Comparison and change use row counts, not currency.
- Reuse the existing trend surface to show matching row counts by year, or omit
  the trend if user testing finds a count trend unhelpful. Do not add a chart.
- `Inspect records` should be the primary action and should focus the existing
  exact-record workspace.

## Computation approach

Consolidate summary work into cached reactive calculations instead of repeating
grouping in multiple outputs.

One historical aggregation can provide, by fiscal year:

- Approved revenue total
- Approved expense total
- Combined approved authority
- Net position
- Matching record count
- Revenue-record count
- Expense-record count

The existing filtered row set and prepared bundle remain the data source. Do
not issue network calls or refresh the ArcGIS source for a drawer selection.

Use the existing deferred heavy-content phase for Plotly and exact rows. Text
identity and summary values should stay outside that heavy gate when doing so
does not risk stale content.

## Responsive behavior

### Desktop and wide tablet

- Keep the right-side drawer and its current width contract.
- Keep title, year, and flow visible without scrolling.
- Allow long department, fund, and category names to wrap.
- Keep the existing bottom action region reachable.

### Mobile and narrow tablet

- Keep the bottom-sheet interaction.
- Use a short eyebrow and a maximum two-line title when practical.
- Let context text and breadcrumbs wrap vertically.
- Do not introduce horizontally scrolling chips.
- Keep summary metrics in one column where the current responsive rules already
  do so.
- Preserve safe-area padding and the current action layout.

Required visual widths are 2048, 1440, 800, and approximately 390 CSS pixels.

## Accessibility requirements

- Preserve one dialog shell and one focus trap.
- Preserve Escape, backdrop, Close, Back, and focus-restoration behavior.
- Keep the visible dynamic title connected to `aria-labelledby`.
- Announce a meaningful context change through the existing polite status
  region.
- Do not rely on accent color to communicate revenue, expenses, net, or records.
- Keep keyboard activation and visible focus for every trigger.
- Preserve reduced-motion behavior.
- Verify that rapid selection changes do not create multiple dialogs or leave
  background content inert after close.

## Performance guardrails

- Keep one persistent drawer shell.
- Add no Plotly instances.
- Add no source or network requests.
- Add no polling, blocking work, or repeated full-page `render.ui` replacement.
- Prefer one cached summary calculation over duplicated aggregations.
- Preserve the existing delayed heavy-content phase unless measurement proves a
  safer faster alternative.
- Preserve background DOM identity while the drawer opens and closes.
- Measure before and after using the same cached local snapshot.

Performance acceptance should include:

- No regression beyond 10 percent in median click-to-open time from the measured
  baseline.
- Context title visible within 500 milliseconds in the cached local demo under
  normal conditions.
- Drawer shell open within the existing tolerant 4-second automated ceiling.
- Drawer close within the existing tolerant 2-second automated ceiling.
- No new Overview recalculation caused only by closing and reopening the same
  context.
- No browser console errors or horizontal overflow.

## Intended implementation surfaces

- `budget_app/state.py`: bounded presentation lens, sanitization, and bookmark
  compatibility.
- `budget_app/application.py`: per-session presentation value, bookmark save and
  restore, and drawer wiring.
- `budget_app/ui/modules/overview.py`: explicit lens on selection requests and
  reset behavior for ordinary filters.
- `budget_app/ui/modules/detail_drawer.py`: pure presentation mapping, contextual
  labels, lens-aware summary formulas, and reused trend surface.
- `www/app.js`: forward the lens with selection payloads only if the existing
  input path cannot do so without client changes. Preserve lifecycle ownership.
- `www/city.css`: small header/accent and wrapping adjustments only. Do not
  change the protected global navigation or footer.
- `tests/test_state.py`: lens sanitization, legacy bookmark compatibility, and
  round-trip coverage.
- A focused presentation unit-test module: identity and label matrix without a
  browser.
- `tests/e2e/test_detail_drawer_contract.py`: visible identity, lens reset,
  lifecycle, performance, focus, overflow, and rapid-switch coverage.

## Implementation sequence

### Phase 0: Baseline and data-language check

1. Record current cached-dataset interaction timings.
2. Capture the current drawer at required widths.
3. Confirm the All Funds percentage denominator. Treat any correction as a
   separate data-language decision if it changes more than drawer presentation.

### Phase 1: Pure presentation mapping

1. Define the bounded lens values.
2. Build the pure mapper and behavior-matrix unit tests.
3. Keep the current rendered behavior unchanged until mapping tests pass.

### Phase 2: State and bookmark integration

1. Store and sanitize the presentation lens.
2. Include it in copied state.
3. Restore legacy bookmarks as `authority`.
4. Verify history, refresh, and shared links.

### Phase 3: Contextual authority drawer

1. Replace generic heading, breadcrumb, metric, trend, and table labels.
2. Cover revenue, expenses, combined authority, year, scope, department, fund,
   category, and ObjectId.
3. Verify mobile wrapping before special modes are added.

### Phase 4: Net Position and Budget Rows

1. Add lens attributes to the two homepage triggers.
2. Reuse summary and trend surfaces with the correct formulas.
3. Make `Inspect records` primary for the source-record lens.
4. Verify all other triggers reset the lens to `authority`.

### Phase 5: Performance and lifecycle validation

1. Run rapid open, close, reopen, switching, browser history, refresh, and
   copied-state journeys.
2. Compare before and after timings.
3. Inspect desktop, tablet, and mobile renders.
4. Correct only regressions attributable to this scope.

## Acceptance scenarios

The implementation is complete only when all of the following are true:

1. Revenue and expenses show distinct titles before the user reads the values.
2. A General Fund selection names General Fund, approved expenses, and FY2027
   in the visible drawer header.
3. A fiscal-year bar names the selected year and retains the active flow and
   scope.
4. Department, fund, category, and ObjectId selections show the complete path.
5. Net Position leads with the same net amount shown on the clicked card.
6. Budget Rows leads with the same record count shown on the clicked card.
7. Clicking a normal scope or hierarchy item after Net Position or Budget Rows
   returns the lens to `authority`.
8. Copied and restored drawer states preserve the intended lens.
9. Desktop drawer and mobile bottom sheet remain responsive and keyboard
   accessible.
10. No additional chart, drawer, source request, or protected-shell change is
    introduced.
11. Performance and DOM-identity gates remain within their recorded budgets.

## Validation commands and evidence

Run the maintained narrow gates first:

```powershell
uv run ruff check --no-cache .
uv run python -m pytest -p no:cacheprovider tests/test_state.py tests/test_components.py
```

Then run the focused drawer browser contract and the existing drilldown audit
helpers against the prepared cached snapshot:

```powershell
uv run python -m pytest -p no:cacheprovider -m e2e tests/e2e/test_detail_drawer_contract.py
uv run python scripts/run_drilldown_followup_audit.py
uv run python scripts/run_final_action_path_audit.py
```

Final evidence must include:

- Changed-file diff review and em dash scan
- Unit and browser-test results
- Before and after interaction timings
- Screenshots at 2048, 1440, 800, and approximately 390 pixels
- No-overflow and console-error results
- Keyboard, focus-restoration, refresh, history, and copied-state results
- Confirmation that the protected navigation and footer did not change

## Non-goals

- A separate Drilldown page or navigation tab
- A new data source, refresh path, cache format, or extraction
- A redesign of the Overview page
- New charts or animation systems
- Changes to the protected global navigation, footer, or City signature
- Claims that approved authority is actual spending, performance, or outcomes
- Resolving the All Funds percentage question without a confirmed denominator
  decision

## Stop and go criteria

Proceed to implementation when the behavior matrix, presentation-lens boundary,
and All Funds denominator treatment are accepted.

Stop and reassess if the change requires a second drawer, another Plotly widget,
a new network request, competing state authority, broad CSS overrides, or a
protected-shell change. Those outcomes would exceed the intended lightweight
clarity pass.
