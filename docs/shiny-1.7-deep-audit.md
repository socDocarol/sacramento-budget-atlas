# Budget Shiny 1.7 Deep Audit

Date: 2026-07-29
Status: PASS
Copy readiness: YES, the repaired `budget-shiny-python` source is ready to copy
Deployment status: Not deployed, published, pushed, or submitted as a pull request

## Executive result

The Budget Shiny application passes the post-upgrade completion gate. The accepted repaired run includes:

- 24 of 24 non-browser tests passed.
- 39 of 39 Chromium end-to-end tests passed in 282 seconds.
- 5 of 5 additional rapid open-close-open repetitions passed with independent lifecycle traces.
- 45 responsive UI audit captures passed across 390, 768, 1024, 1440, and 1920 CSS pixel widths.
- 12 focused drawer and workspace captures passed, including 125%, 150%, and 200% effective zoom widths.
- Ten simultaneous browser sessions reached ready state with no failures and isolated session state.
- Production-mode startup returned HTTP 404 for the Shiny test snapshot endpoint.
- Browser runs produced no console errors, page errors, failed requests, HTTP errors, or WebSocket errors.

The verified Shiny 1.7 compatibility defect was a stale drawer lifecycle message that could win a rapid open-close-open race. The repaired client and server now use a monotonic lifecycle generation, ignore stale lifecycle messages, and declare the drawer open only after the current CSS animation completes. This is guarded by state-based waits and five repeated traces.

The audit also removed repeated overview selection sanitization within the same reactive invalidation, added explicit data-load timing and cache-path provenance, replaced the deprecated download renderer, exported safe test state through `AppTestValues`, and corrected the accessibility audit so controls under inert or `aria-hidden="true"` ancestors are treated as unavailable.

## Scope and boundaries

The audit inspected and repaired only `budget-shiny-python`, plus the required completion record under `orchestration/shiny-1.7/state/`.

The following boundaries were preserved:

- City platform source was not modified.
- Research source and its completion record were not modified.
- Next.js Budget applications were not modified.
- Fancy application source was not created or modified by this audit.
- No deployment, publication, push, or pull request occurred.
- City data meaning, exact source fields, source attribution, and exact-data alternatives were preserved.
- Approved-budget versus actual-spending caveats were preserved.
- Analytical limitations and non-causal wording were preserved.
- Data-owner approval boundaries were preserved.

## Required-file and instruction review

The audit read the complete required upgrade and project materials before repair work:

- `orchestration/shiny-1.7/MASTER_PLAN.md`
- `orchestration/shiny-1.7/state/UPGRADE_COMPLETE.md`
- `orchestration/shiny-1.7/reports/SHINY_1_7_UPGRADE_REPORT.md`
- Root and applicable parent/project `AGENTS.md` files
- `budget-shiny-python/README.md`
- `budget-shiny-python/docs/validation-report.md`
- `budget-shiny-python/docs/stability-performance-layout-completion.md`
- Existing Budget UI audit and validation evidence
- `.agents/skills/shiny-for-python/SKILL.md`

## Exact Shiny skill references used

The following reference files were read completely and used during the audit:

1. `.agents/skills/shiny-for-python/references/reactivity.md`
2. `.agents/skills/shiny-for-python/references/modules-core.md`
3. `.agents/skills/shiny-for-python/references/session-lifecycle.md`
4. `.agents/skills/shiny-for-python/references/layouts.md`
5. `.agents/skills/shiny-for-python/references/navigation.md`
6. `.agents/skills/shiny-for-python/references/dynamic-ui.md`
7. `.agents/skills/shiny-for-python/references/plots.md`
8. `.agents/skills/shiny-for-python/references/data-frames.md`
9. `.agents/skills/shiny-for-python/references/files.md`
10. `.agents/skills/shiny-for-python/references/feedback.md`
11. `.agents/skills/shiny-for-python/references/bookmarking.md`
12. `.agents/skills/shiny-for-python/references/custom-components.md`
13. `.agents/skills/shiny-for-python/references/testing.md`
14. `.agents/skills/shiny-for-python/references/debugging.md`
15. `.agents/skills/shiny-for-python/references/theming.md`
16. `.agents/skills/shiny-for-python/references/extended-tasks.md`
17. `.agents/skills/shiny-for-python/references/otel.md`

## Preserved baseline

The baseline was measured before repairs and was not rerun after the interrupted prior turn.

### Baseline functional result

The baseline full browser suite completed with 33 passed, 1 failed, 24 deselected, and 1 upstream warning in 328.50 seconds. The failure was:

`test_rapid_open_close_open_and_repeated_cycles_leave_one_clean_shell`

After rapid open-close-open activity, an older `closing` lifecycle message could overwrite the newer open request. The visible result was a closing or hidden drawer with the body scroll lock still applied.

Evidence:

- `artifacts/shiny-1.7-audit/before/e2e/full-e2e.summary.json`
- `artifacts/shiny-1.7-audit/before/e2e/`

### Baseline runtime

The warm runtime probe measured:

| Metric | Baseline |
|---|---:|
| Response start | 35.3 ms |
| DOM content loaded | 218.0 ms |
| Load event end | 392.4 ms |
| Drawer shell feedback | 10.6 ms |
| Stable drawer visual | 245.7 ms |
| Warm summary | 202.1 ms |
| Progressive chart ready | 2,203.7 ms |
| Close visual | 19.1 ms |
| Lifecycle cleanup | 192.7 ms |
| Output recalculation settle | 49.01 ms |
| Long tasks | 11 |
| Longest long task | 1,257 ms |

All baseline responsive widths had zero document overflow, one visible H1, and one main landmark. Keyboard and reduced-motion checks passed outside the identified lifecycle race.

Evidence:

- `artifacts/shiny-1.7-audit/before/warm-runtime/runtime/runtime-metrics.json`

### Baseline data and concurrency performance

| Path or action | Baseline |
|---|---:|
| Cold HTTP ready | 2,754.59 ms |
| Cold ArcGIS first useful UI | 19,866.59 ms |
| What Changed navigation | 82.40 ms |
| Explorer first grid | 2,241.86 ms |
| Explorer filter settle | 2,054.36 ms |
| Warm in-process first useful UI | 3,858.90 ms |
| Warm restart HTTP ready | 3,737.16 ms |
| Warm restart first useful UI | 5,655.01 ms |
| Stale-cache HTTP ready | 2,688.21 ms |
| Stale-cache first useful UI | 9,093.11 ms |
| Ten sessions ready | 10 |
| Ten-session failures | 0 |
| Ready RSS delta | 64.91 MiB |
| Post-close RSS residual | 58.13 MiB |

Evidence:

- `artifacts/shiny-1.7-audit/before/performance/metrics.json`
- `artifacts/shiny-1.7-audit/before/profile/metrics.json`

## Repairs

### Drawer lifecycle race

The server now sends a monotonically increasing lifecycle generation with each drawer lifecycle message. The browser ignores any lifecycle message older than the current generation. A newer open request can supersede a closing state. The browser sets lifecycle state to `open` only after the current CSS animation completes, guarded by the active transition token.

This repair preserves the persistent shell, history integration, focus restoration, inert background behavior, scroll locking, reduced motion, and bookmark restoration.

### Reactive recomputation

Overview selection sanitization now runs through one reactive calculation per source or selection invalidation. Downstream outputs consume that shared state instead of repeatedly calling the sanitizer. The repaired runtime probe reduced output recalculation settle time from 49.01 ms to 28.11 ms.

### Data provenance and timing

Repository results now expose:

- Cache source: `memory`, `disk-fresh`, `disk-revalidated`, `source`, or `stale-disk`
- Load elapsed time in milliseconds

The repository records explicit timing and path status for memory, fresh disk, revalidated disk, live source, and stale fallback paths. The application exports the safe status through test mode without changing user-facing data meaning.

### Shiny 1.7 test mode

Local automated server fixtures set `SHINY_TESTMODE=1`. Production-mode fixtures explicitly remove it. Application startup does not enable test mode.

Safe exports cover:

- Application source and cache state
- Stale snapshot state
- Overview state
- Explorer filtered, rendered, visible, and selected exact ObjectIds
- Selected departments

Snapshot preprocessors scrub or reset nondeterministic action counters for share, retry, reset, and copy actions.

### DataGrid and Plotly

The Explorer download renderer now uses `@render.download_button`.

Controller tests verify DataGrid rendering, filtering, sorting, selection, and exact ObjectId agreement between browser state and exported server state. Plotly tests verify bar and scatter coordinated selection in What Changed, and they wait for the drawer lifecycle to reach the expected state.

### Accessibility audit

The UI audit now treats a control as unavailable when any ancestor is inert or has `aria-hidden="true"`. This removes a false positive caused by counting modal-background controls that are intentionally removed from the accessibility tree.

## Final validation

### Unit, syntax, and package gates

| Gate | Result |
|---|---|
| `ruff format --check budget_app scripts tests` | PASS, 47 files already formatted |
| `ruff check budget_app scripts tests` | PASS |
| `python -m compileall -q budget_app scripts tests` | PASS |
| `node --check www/app.js` | PASS |
| `uv lock --check` | PASS, 86 packages resolved |
| `pytest -q tests -m "not e2e"` | PASS, 24 passed |

The only Python warning is the upstream `shinywidgets` `Widget.widgets` deprecation.

### Browser and controller gates

The accepted full browser run completed with 39 passed, 0 failed, and 1 upstream warning in 282 seconds.

It includes:

- Shiny `AppTestValues` server-state inspection
- Snapshot preprocessing
- Production snapshot endpoint rejection
- Live, error, and stale-cache paths
- DataGrid render, filter, sort, selection, and exact-data agreement
- Plotly bar and scatter coordinated selection
- Drawer rapid cycles, persistent shell, hierarchy, exact records, and workspace
- Navigation, browser history, bookmarks, legacy links, and focus restoration
- Reduced motion and keyboard focus trapping
- Ten-session isolation

The corrected DataGrid controller test passed in 5.85 seconds. The repaired rapid lifecycle test passed in 6.06 seconds within the aggregate run.

Evidence:

- `artifacts/shiny-1.7-audit/after/e2e/final-full-e2e.log`
- `artifacts/shiny-1.7-audit/after/rapid-repetitions/summary.json`
- `artifacts/shiny-1.7-audit/after/rapid-repetitions/run-01/` through `run-05/`

The five additional rapid lifecycle repetitions all returned code 0 and produced a lifecycle trace:

| Run | Duration |
|---|---:|
| 1 | 12,843 ms |
| 2 | 13,891 ms |
| 3 | 12,937 ms |
| 4 | 13,047 ms |
| 5 | 12,391 ms |

### Runtime gate

| Metric | Before | After |
|---|---:|---:|
| Response start | 35.3 ms | 30.9 ms |
| DOM content loaded | 218.0 ms | 201.1 ms |
| Load event end | 392.4 ms | 380.5 ms |
| Drawer shell feedback | 10.6 ms | 8.6 ms |
| Stable drawer visual | 245.7 ms | 231.5 ms |
| Warm summary | 202.1 ms | 100.1 ms |
| Progressive chart ready | 2,203.7 ms | 1,763.5 ms |
| Close visual | 19.1 ms | 54.9 ms |
| Lifecycle cleanup | 192.7 ms | 209.3 ms |
| Lifecycle closed | 192.6 ms | 209.1 ms |
| Output recalculation settle | 49.01 ms | 28.11 ms |
| Long tasks | 11 | 8 |
| Longest long task | 1,257 ms | 790 ms |

Every hard acceptance budget passed. Chart rendering remains explicitly progressive and has no hard budget.

Evidence:

- `artifacts/shiny-1.7-audit/after/runtime/runtime-metrics.json`
- `artifacts/shiny-1.7-audit/after/runtime/`

### Responsive, accessibility, keyboard, and zoom gate

The responsive UI audit captured nine application states at five widths, for 45 screenshots total. It verified one main landmark, one visible H1, no document overflow, no inappropriate perceivable modal-background controls, and usable navigation and controls.

The focused visual pass captured 12 additional states:

- Department detail at 1024, 1440, and 1920 CSS pixels
- Mobile bottom sheet at 390 CSS pixels
- Expanded workspace at 1440 CSS pixels
- Fund, category, exact record, and longest breadcrumb states
- Effective 125%, 150%, and 200% zoom widths

All 12 focused states reported zero root overflow, zero body overflow, and zero metric overflow. The 200% state correctly used the mobile bottom-sheet layout.

Keyboard and motion results:

- Skip link focused successfully.
- Skip link moved focus to main.
- Reverse Tab remained within the open detail surface.
- Close restored focus to the trigger.
- Reduced-motion media query matched.
- Transition and animation durations reduced to `1e-06s`.
- Final page state had no dialogs, inert nodes, or scroll lock.

Evidence:

- `artifacts/shiny-1.7-audit/after/ui-r2/`
- `artifacts/shiny-1.7-audit/after/visual-final/capture-summary.json`
- `artifacts/shiny-1.7-audit/after/visual-final/`
- `artifacts/shiny-1.7-audit/after/runtime/runtime-metrics.json`

### Console, request, and WebSocket gate

Each cold, warm in-process, warm restart, and stale-cache browser capture recorded:

- 0 console errors
- 0 page errors
- 0 failed requests
- 0 HTTP errors
- 0 WebSocket errors
- 1 active Shiny WebSocket with sent and received frames

Each capture recorded the same five upstream `bootstrap-datepicker` locale deprecation warnings. These are dependency warnings, not application failures.

The captured `closed=false` WebSocket field is expected because the performance harness snapshots the event record before closing the browser context. It is not a failure signal. Each socket had zero errors.

### Memory and ten-session gate

All ten simultaneous sessions became ready, produced no failures, and maintained isolated server state.

| Metric | Before | After |
|---|---:|---:|
| Ready sessions | 10 | 10 |
| Failures | 0 | 0 |
| Isolated session state | Yes | Yes |
| Ready RSS delta | 64.91 MiB | 68.98 MiB |
| Post-close RSS residual | 58.13 MiB | 34.29 MiB |

The ready RSS delta increased by 4.07 MiB while the post-close residual decreased by 23.85 MiB. No session readiness or isolation regression was observed.

## Diagnostic attempts retained

The evidence directory retains unsuccessful post-repair diagnostic attempts for traceability:

- One wrapper used its default port 8000 and received connection refused.
- One run used millisecond values where `AppTestValues` expected seconds and timed out.
- One run sampled viewport geometry during the drawer CSS transition and observed a temporary 1.8 to 2.5 pixel overshoot.
- The first UI audit counted inert modal-background controls, which was a probe defect.

Each issue was corrected in the harness or wait condition. The accepted evidence is the 39-test foreground run, five lifecycle repetitions, `ui-r2`, `visual-final`, final runtime probe, final performance run, and final unit gate. No failed diagnostic attempt is represented as an accepted result.

## Changed source and test files

The workspace has no enclosing Git repository, so ownership was tracked through the explicit repair set and final SHA-256 hashes.

| File | Purpose | SHA-256 |
|---|---|---|
| `budget_app/data/models.py` | Cache path and elapsed-time result types | `14d843c00f5c201ebf029f89f79c6c938ce42bbd972adfa5e1f02cf687f8fa15` |
| `budget_app/data/repository.py` | Explicit cache-path timing and logging | `7575555244f7b61d1760242965ca8fc33e8adae24236d045c0c27741fb779d5e` |
| `budget_app/application.py` | Refresh timing and safe application test export | `4971e23f5032bfe15334e8e86c9f3a4cbdb75f216fe31797f81f98dd1672b4ba` |
| `budget_app/ui/modules/overview.py` | Shared sanitized reactive state and test export | `146a0eab66c71a7967c2769597cf4d5549a3edfb0f2fddfacd9978272d660f93` |
| `budget_app/ui/modules/explorer.py` | Shiny 1.7 download renderer and exact DataGrid test export | `5b5aaf95175d92d747335860b02c1bec2511717a07c85018e0ff9933aada0d69` |
| `budget_app/ui/modules/detail_drawer.py` | Monotonic lifecycle generation | `445cd7362ad57a6ca2937dc4aec63d3f9bbf1418969f429e5a24c36717bb7350` |
| `www/app.js` | Stale lifecycle rejection and animation-complete state | `4be97ff9c6e22243e08b63ebff7cf88e4ba98da502b4a66e3e22bcbda52e41bc` |
| `tests/e2e/conftest.py` | Local test mode, stale fixture, production-mode fixture | `7f1f5a6a1f63dcc3b4bfadd6406f82d98bfce8cd2d051e93eb12b58e3483e237` |
| `tests/e2e/test_shiny_17_contract.py` | Controller, AppTestValues, Plotly, stale, and production tests | `0219fc742d01ee058b85b95f29cc9506e9b295929bac74a764d65a59d5d40d2a` |
| `tests/test_data_repository.py` | Cache source and timing assertions | `6b44f31c07048111cd36e8fe087588ea8706269e562e69067d49ec2366c6b461` |
| `scripts/run_shiny_17_performance_audit.py` | Cold, warm, stale, request, WebSocket, trace, and concurrency audit | `e798d45f4cf8ced44056d7f29556cc002ef7c534137c87ed34e6558bb260ebbf` |
| `scripts/profile_shiny_17_hotspots.py` | Deterministic profiling and explicit hotspot timers | `de01dba1ee9dc3ac24362425b78114c5ccc56a4727a7a9f7b9c28a2736d90ddf` |
| `scripts/capture_ui_audit.py` | Correct inert and hidden ancestor accessibility probe | `5e0b8d7b793cba77f37c6c565775d20f78575510197b28217f9942f64147d1c1` |

This report and `docs/shiny-1.7-performance-before-after.md` are audit deliverables added by this work. The completion state file is written under `orchestration/shiny-1.7/state/` after the required Fancy launch is verified. Generated evidence files are enumerated by `artifacts/shiny-1.7-audit/manifest.sha256`.

## Known limitations

- Real ArcGIS cold-path timing includes network and upstream-service variance. The final cold first-useful result was 2.5% slower than baseline, while warm and stale first-useful paths improved. The audit does not claim that one cold sample proves a regression or an improvement.
- Plotly initialization still creates browser long tasks. The longest observed task improved from 1,257 ms to 790 ms, and chart loading remains progressive.
- The application inherits five `bootstrap-datepicker` locale deprecation warnings from its dependency bundle.
- The Python suite inherits one `shinywidgets` deprecation warning.
- Zoom evidence uses equivalent effective CSS widths rather than operating-system UI automation of the browser zoom menu.
- The performance event snapshot occurs before browser-context shutdown, so its WebSocket record is still open at capture time. It has zero errors.
- This is a local audit. Hosting, authentication, gateway, and production concurrency remain deployment-environment responsibilities.

## Multi-agent execution record

Two bounded depth-one workers assisted the audit:

- `luna_worker`, fixed xhigh effort: performance, process, and evidence inventory
- `luna_frontend`, fixed xhigh effort: responsive, interaction, and accessibility inventory

Unique child count: 2
Maximum delegation depth: 1
Model-routing fallback: None observed

The root Sol agent inspected the underlying files, test logs, JSON metrics, process state, screenshots, and final gate outputs. Worker summaries were not used as acceptance evidence by themselves.

## Acceptance decision

PASS. The repaired Budget source is ready to copy. The Shiny 1.7 compatibility race is repaired, the required local-only test-mode controls are in place, controller state is safely observable, performance and concurrency evidence is preserved, and the complete unit, browser, accessibility, warning, request, and visual gates pass.

## Post-gate Fancy launch

The valid research gate was read completely after the Budget gate passed. The required immutable Fancy prompt was then passed once to the project-chat launcher.

- Project: `Data Storyboard`
- Applied title: `[Data Storyboard - 07/29] Fancy Budget Shiny Build`
- Thread ID: `019fadf8-7f7b-7320-b421-ae40ed3b2f36`
- Prompt SHA-256 before and after launch: `49f783fbfb14918df0611edf972ac46aa52f604a4765a03a4e3d80731352a506`
- `recentChatsDiscoverable=true`
- `codexTabVisible=true`, rank 1
- Post-launch activity: one assistant commentary message and four tool calls observed
- Explicit VS Code open: exit code 0 for `vscode://openai.chatgpt/local/019fadf8-7f7b-7320-b421-ae40ed3b2f36`

Evidence:

- `artifacts/shiny-1.7-audit/fancy-launch/launch-evidence.json`
- `orchestration/shiny-1.7/state/BUDGET_AUDIT_COMPLETE.md`
