# Sacramento Budget Shiny Stability, Performance, and Layout Completion

Completion date: July 28, 2026

## Status

The stability, performance, desktop layout, mobile sheet, accessibility, and
validation work is complete for the local Sacramento Approved Budget Shiny
pilot.

The final implementation retains one persistent detail shell, isolates drawer
state from Overview analytics, renders usable detail progressively, preserves
bookmark and browser-history behavior, and fits the required desktop and mobile
widths. All interaction-critical performance budgets passed. The final
acceptance matrix contains no unresolved medium, high, or critical findings.

This is a local technical completion. No deployment, push, or pull request was
performed. City data-owner approval remains required before leadership use.

## Problems addressed

The work focused on these observed risks:

- Drawer markup and Shiny outputs could be replaced during interaction.
- Drawer-only selections could trigger unnecessary Overview recalculation.
- Open, close, rapid reopen, hierarchy changes, and focus restoration could
  compete with reactive rendering.
- Heavy detail outputs could delay the first usable drawer state.
- Background content could fade, flash, or briefly expose stale detail while
  the drawer changed context.
- Desktop width, long values, mobile safe areas, zoom reflow, and modal cleanup
  needed explicit verification.
- Existing checks did not fully cover repeated lifecycle actions, same-context
  reopen, ten-session isolation, or every required evidence surface.

## Implementation

### Persistent detail shell

`budget_app/ui/modules/detail_drawer.py` now defines one static overlay and
dialog shell. The server updates the shell's outputs and desired state without
remounting the outer element.

The shell has explicit closed, opening, open, and closing lifecycle states. The
final browser contract verifies:

- One shell exists before, during, and after interaction.
- The shell retains its DOM identity across close, reopen, and hierarchy
  changes.
- Close cleanup removes scroll locking and inert markers.
- No focus remains inside a hidden drawer.
- Header Close, footer Close, backdrop, Escape, browser Back, Clear, and
  hierarchy Back all use the same lifecycle.

### Analytics and presentation state separation

`budget_app/application.py` maintains separate state authorities:

- `overview_selection` for the visible Overview analytics context.
- `detail_selection` for quick-detail context.
- `drawer_desired_open` for drawer presentation.
- `workspace_desired_open` for expanded analysis presentation.

Drawer-only actions update `detail_selection` without committing a new
`overview_selection`. An explicit Expand analysis or Inspect records action is
required before the shared Overview workspace changes.

The legacy bookmark shape is preserved by composing selection and presentation
state at the bookmark boundary. Drawer, workspace, hierarchy, filters, and
selected-record state continue to restore through bookmarks and browser
history.

### First-open and same-context isolation

The final first-open contract closes the drawer, waits two seconds for
quiescence, and then confirms:

- `overviewRecalculations == 0`
- Overview opacity remains `1`
- No Overview output is busy
- Exactly one detail shell remains

The same-context reopen contract also records zero Overview recalculations.
Client-side selection classes preserve the selected movement after close and
are removed by Reset, Back, or Clear without forcing an Overview rerender.

### Progressive detail rendering

Heavy detail work is deferred until after the shell is usable. Detail content
is cached by context so reopening the same selection can reuse completed
content.

The client marks detail content as pending, loading, or ready. While loading,
stale metric text is hidden and a scoped progressive state is shown. The
historical chart remains progressive and is not part of the interaction-ready
budget.

The final semantic change summary separates:

- Change amount
- Change percentage
- Plain-language explanation

### Client lifecycle, focus, and history

`www/app.js` coordinates the persistent shell. It includes:

- Explicit lifecycle transitions and transition-end cleanup.
- Scroll locking and scoped inert behavior.
- Focus trapping while the dialog is open.
- Synchronous focus restoration with a deferred visible-trigger fallback.
- Cancellation of pending focus restoration when the user begins another
  action.
- Browser-history synchronization without duplicate shells.
- Scoped mutation observers. No body-wide mutation observer is attached.
- Priming for supported DataGrid rows and Plotly marks during a settling close.
- A controlled reopen request when the same trigger is activated before close
  cleanup completes.

### Responsive layout and accessibility

`www/city.css` establishes:

- A 90rem analysis canvas for the major application views.
- A desktop drawer width of `clamp(600px, 46vw, 760px)`.
- A viewport-capped mobile bottom sheet with safe-area padding.
- Wrapping and containment for long metric, count, and breadcrumb values.
- Scoped recalculation-opacity behavior so background content remains stable.
- Reduced-motion behavior for the drawer and loading treatment.
- Visible focus and modal states compatible with keyboard navigation.

Required geometry passed at 390, 768, 1024, 1440, and 1920 CSS pixels. The
125%, 150%, and 200% zoom-equivalent checks also recorded zero page, body, and
metric overflow.

### Data refresh and cache behavior

The application does not download the full ArcGIS source for every visitor.

- The default cache lifetime is 86,400 seconds, or 24 hours.
- A fresh in-memory snapshot is reused across sessions in the same process.
- A fresh local Parquet snapshot is used after a process restart.
- When the cache expires, the repository checks the ArcGIS layer metadata.
- If the source edit timestamp has not changed, the disk snapshot remains in
  use.
- Ordered 1,000-row ArcGIS pages are downloaded only when the source changed,
  metadata checking cannot confirm the cached version, or a manual source
  Refresh is requested.
- If refresh fails and a valid disk snapshot exists, the application serves it
  with a stale-data warning.

Occasional slow startup is therefore more closely associated with per-session
Shiny output creation, Plotly rendering, concurrent cold sessions, or an
expired cache than with a full source download on every visit.

## Performance results

| Metric | First authoritative run | Repeat run | Acceptance budget |
| --- | ---: | ---: | ---: |
| Shell feedback | 10.2 ms | 7.1 ms | 300 ms |
| Stable visual | 274.0 ms | 236.3 ms | 300 ms |
| Warm summary | 274.0 ms | 170.6 ms | 1,200 ms |
| Progressive chart | 3,634.8 ms | 2,019.2 ms | No hard budget |
| Close visual | 0.7 ms | 38.5 ms | 300 ms |
| Cleanup | 221.3 ms | 230.5 ms | 500 ms |
| Lifecycle closed | 221.1 ms | 230.4 ms | 500 ms |

Both runs retained the shell, recorded zero shell replacements, and had no
browser or server errors.

Compared with the instrumented baseline:

- Long-task count fell from 48 to 13 on the first final run and 8 on repeat.
- Observed mutations fell from 38,396 to 5,820, an 84.8% reduction.
- The longest long task increased from 821 ms to 1,187 ms on the first run and
  1,027 ms on repeat. This remains a low-severity Plotly and rendering concern,
  not an interaction-budget failure.

## Validation results

### Automated checks

- Non-live unit suite: 23 passed, 35 deselected.
- Focused lifecycle suite: 5 passed, 53 deselected.
- Authoritative browser suite: 34 passed, 24 deselected, 0 failed in
  352.67 seconds.
- Final action-path audit: 11 of 11 passed.
- Ten-session browser isolation contract: passed.
- Ruff static analysis: passed.
- Ruff format check: 45 files already formatted.
- JavaScript syntax: passed with `node --check www/app.js`.
- Python compilation: passed.
- Scoped U+2014 scan: passed.
- Final artifact manifest: 72 files, all SHA-256 values verified.

The only automated warning is the installed `shinywidgets.Widget.widgets`
deprecation warning.

### Interaction coverage

The final paths cover:

- All four Overview KPI cards.
- Overview trend-chart marks.
- Department, fund, category, and exact-record detail.
- Header Close, footer Close, backdrop, Escape, Clear, Expand analysis, Inspect
  records, workspace Back, and hierarchy Back.
- Rapid open, close, reopen, and five repeated cycles.
- Same-context reopen.
- Bookmark restore, refresh, browser Back, and browser Forward.
- Keyboard navigation, skip link, focus trap, focus restoration, and reduced
  motion.
- Fresh loading, complete source error, and stale repository fallback.
- Mobile menu and bottom-sheet behavior.
- Ten simultaneous isolated Shiny sessions.

The source Refresh control was not clicked during the final browser acceptance
run. The audited browser reload used the cached local server and confirmed
`externalRefreshCalled: false`.

### Concurrent readiness

The first asynchronous load run had 9 of 10 sessions ready within 30 seconds.
One cold session timed out before isolation could be evaluated. A second run
with a 60-second readiness bound had 10 of 10 sessions ready, no failures, and
isolated session state.

This is recorded as a low-severity cold-start limitation rather than hidden by
the successful rerun.

### Visual evidence

The final package contains:

- Thirty standard screenshots covering all six public views at 390, 768, 1024,
  1440, and 1920 widths.
- Department drawer captures at 1024, 1440, and 1920.
- Fund, category, exact-record, longest-label, and expanded-workspace captures.
- A 390px mobile bottom-sheet capture.
- 125%, 150%, and 200% zoom-equivalent captures.
- First-run and repeat-run open and closed drawer captures.
- An 18.36-second lifecycle recording and extracted contact sheet.

Root visual review found no medium-or-higher visual or accessibility issue. At
1024px, the native Budget flow select truncates its visible label. The complete
meaning remains visible in the active-context chip below it, so this is retained
as a low-severity polish item.

## Changed implementation surfaces

Production content changes:

- `budget_app/application.py`
- `budget_app/ui/modules/detail_drawer.py`
- `budget_app/ui/modules/overview.py`
- `www/app.js`
- `www/city.css`

`budget_app/state.py` was inspected and included in final source hashing, but
its final content matches the baseline.

Test changes:

- `tests/test_state.py`
- `tests/e2e/conftest.py`
- `tests/e2e/test_app.py`
- `tests/e2e/test_detail_drawer_contract.py`

Audit and evidence tooling:

- `scripts/load_test.py`
- `scripts/run_drilldown_followup_audit.py`
- `scripts/run_e2e_with_diagnostics.py`
- `scripts/run_rapid_cycle_repetitions.py`
- `scripts/capture_ui_audit.py`
- `scripts/capture_final_drawer_evidence.py`
- `scripts/build_capture_contact_sheet.py`
- `scripts/run_final_action_path_audit.py`
- `scripts/write_audit_hashes.py`

## Authoritative evidence

The final evidence root is:

`artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/`

Primary files:

- [Acceptance matrix](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/audit-matrix.md)
- [Full browser log](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/e2e/full-e2e.stdout.log)
- [Browser summary](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/e2e/full-e2e.summary.json)
- [First runtime metrics](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/runtime/runtime-metrics.json)
- [Repeat runtime metrics](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/runtime-repeat/runtime-metrics.json)
- [Action-path audit](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/action-paths-rerun/action-path-audit.json)
- [Required-capture summary](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/required-surfaces/capture-summary.json)
- [Screenshot contact sheet](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/contact-sheet.html)
- [Recording contact sheet](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/runtime/recording/open-close-contact-sheet.png)
- [Production source hashes](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/production-source-sha256.txt)
- [Artifact hash manifest](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/hashes.json)
- [Server verification](../artifacts/ui-audit/drilldown-follow-up/final/authoritative-r8/server-verification.txt)

The exact-final acceptance server was verified at `http://127.0.0.1:8002`
against the final source state.

## Known limitations and follow-up boundaries

- Plotly detail charts remain progressive and can take 2.0 to 3.6 seconds.
- The longest observed main-thread task remains above one second.
- A cold set of ten concurrent sessions may need more than 30 seconds.
- The 1024px native flow label has a low-severity visual truncation.
- Stale and empty final-source UI states were not forced against the
  authoritative server. Stale repository fallback and the complete source-error
  UI were tested.
- Chrome DevTools MCP was unavailable. Browser validation used Playwright.
- The project directory is not a Git worktree, so final scope verification used
  SHA-256 hashes.
- One read-only live ArcGIS contract was run unintentionally when an explicit
  pytest marker expression overrode the default live-test exclusion. It passed
  and made no external changes, but refreshed the scoped `.cache` Parquet and
  metadata files. Final acceptance relies on the subsequent non-live unit run
  and cached local server evidence.
- Technical acceptance does not replace the City data-owner review in
  `docs/data-owner-review.md`.

## Multi-agent execution record

Three first-tier GPT-5.6 Terra agents ran at xhigh effort:

- Lifecycle and state implementation.
- Responsive visual and accessibility implementation and review.
- Adversarial tests, action audits, load checks, captures, and artifact
  packaging.

Unique child count was three. Second-tier child count was zero. Maximum
delegation depth was one. No model-routing fallback occurred.

The GPT-5.6 Sol root owned architecture, integration, final production
corrections, and acceptance. Root validation directly inspected the source,
hashes, unit and browser results, server evidence, runtime metrics, screenshots,
recording frames, matrix, and final artifact manifest.
