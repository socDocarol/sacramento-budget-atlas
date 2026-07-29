# Budget Shiny 1.7 Performance Before and After

Date: 2026-07-29
Result: PASS

## Measurement method

The same local audit harness measured the preserved baseline and repaired application. The harness used:

- A clean cache for cold ArcGIS startup
- An in-process second browser session for warm behavior
- A server restart against the populated cache
- A forced stale-cache path with source failure
- Browser navigation and state-based first-useful waits
- DataGrid render and filter waits
- Browser console, request, response, and WebSocket capture
- Playwright traces and screenshots
- Ten simultaneous browser sessions
- Process RSS sampling before readiness, after readiness, and after close
- Explicit Python timers and `cProfile` for data and reactive hotspots

Shiny test mode was enabled only for local automated test launches. The production-mode endpoint check returned HTTP 404.

## Startup and first-useful results

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Cold HTTP ready | 2,754.59 ms | 3,303.99 ms | +19.9% |
| Cold ArcGIS first useful UI | 19,866.59 ms | 20,356.91 ms | +2.5% |
| Cold DOM content loaded | 468.68 ms | 623.50 ms | +33.0% |
| Warm in-process first useful UI | 3,858.90 ms | 3,056.95 ms | -20.8% |
| Warm restart HTTP ready | 3,737.16 ms | 3,231.46 ms | -13.5% |
| Warm restart first useful UI | 5,655.01 ms | 4,783.53 ms | -15.4% |
| Stale-cache HTTP ready | 2,688.21 ms | 3,245.43 ms | +20.7% |
| Stale-cache first useful UI | 9,093.11 ms | 8,566.05 ms | -5.8% |

The cold and stale HTTP-ready samples were slower, while the user-visible warm and stale first-useful paths improved. Cold ArcGIS first-useful time was 490.32 ms slower, a 2.5% difference within a single network-dependent sample. This is retained as observed evidence, not normalized away.

All cases reached the expected source status:

- Cold ArcGIS: fresh
- Warm in-process: fresh
- Warm restart: fresh
- Forced stale source failure: warning with usable stale data

## Navigation and first interaction

| Metric | Before | After | Change |
|---|---:|---:|---:|
| What Changed navigation | 82.40 ms | 120.81 ms | +46.6% |
| Explorer first grid | 2,241.86 ms | 2,087.96 ms | -6.9% |
| Explorer filter settle | 2,054.36 ms | 1,686.87 ms | -17.9% |

The navigation sample increased by 38.41 ms but remained a fast first interaction. Grid display and filter settlement improved.

## Drawer and reactive runtime

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Response start | 35.3 ms | 30.9 ms | -12.5% |
| DOM content loaded | 218.0 ms | 201.1 ms | -7.8% |
| Load event end | 392.4 ms | 380.5 ms | -3.0% |
| Drawer shell feedback | 10.6 ms | 8.6 ms | -18.9% |
| Stable drawer visual | 245.7 ms | 231.5 ms | -5.8% |
| Warm summary | 202.1 ms | 100.1 ms | -50.5% |
| Progressive chart ready | 2,203.7 ms | 1,763.5 ms | -20.0% |
| Close visual | 19.1 ms | 54.9 ms | +187.4% |
| Cleanup | 192.7 ms | 209.3 ms | +8.6% |
| Lifecycle closed | 192.6 ms | 209.1 ms | +8.6% |
| Output recalculation settle | 49.01 ms | 28.11 ms | -42.6% |
| Long-task count | 11 | 8 | -27.3% |
| Longest long task | 1,257 ms | 790 ms | -37.2% |

Every hard runtime budget passed:

- Shell feedback: under 300 ms
- Stable visual: under 300 ms
- Warm summary: under 1,200 ms
- Close visual: under 300 ms
- Cleanup and lifecycle closed: under 500 ms

Chart readiness is intentionally progressive and has no hard acceptance budget.

The close path is slightly slower because lifecycle completion now follows the actual current animation instead of accepting a stale message. It remains well under its 300 ms visible-close budget, and the repaired race passed the aggregate test plus five independent repeated traces.

## Targeted Python profiling

The profile used the same 29,387-row parquet snapshot spanning fiscal years 2013 through 2027.

| Timer | Before median | After median | Change |
|---|---:|---:|---:|
| Parquet read | 4.446 ms | 4.039 ms | -9.2% |
| Normalize frame | 287.014 ms | 293.713 ms | +2.3% |
| Build snapshot | 70.853 ms | 69.037 ms | -2.6% |
| Overview current rows | 1.190 ms | 1.336 ms | +12.3% |
| Overview comparison rows | 1.152 ms | 1.080 ms | -6.3% |
| Overview history rows | 0.290 ms | 0.244 ms | -15.9% |

These isolated function timings show small run-to-run variation and no material pure-function regression. The overview repair is structural: it avoids repeated state sanitization within one reactive invalidation. Its application-level effect is reflected in the 42.6% faster output recalculation settlement.

Evidence:

- `artifacts/shiny-1.7-audit/before/profile/metrics.json`
- `artifacts/shiny-1.7-audit/after/profile/metrics.json`
- `artifacts/shiny-1.7-audit/after/profile/hotspots.prof`
- `artifacts/shiny-1.7-audit/after/profile/hotspots.txt`

## Browser requests and WebSocket behavior

The final cold, warm in-process, warm restart, and stale captures each recorded:

| Signal | Result per capture |
|---|---:|
| Console warnings | 5 |
| Console errors | 0 |
| Page errors | 0 |
| Failed requests | 0 |
| HTTP errors | 0 |
| Shiny WebSockets | 1 |
| WebSocket errors | 0 |

The five warnings are inherited `bootstrap-datepicker` locale deprecations. They are identical across paths.

The event record is written before the browser context closes, so the socket has `closed=false` at capture time. Frame traffic and zero socket errors confirm that the measured connection was active and healthy during the scenario.

## Ten-session memory and isolation

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Sessions ready | 10 | 10 | No change |
| Failures | 0 | 0 | No change |
| Session state isolated | Yes | Yes | No change |
| Ready RSS delta | 64.91 MiB | 68.98 MiB | +4.07 MiB |
| Post-close RSS residual | 58.13 MiB | 34.29 MiB | -23.85 MiB |

All ten sessions became useful. Individual ready times in the repaired run ranged from 3,478.61 ms to 17,015.72 ms. The server preserved per-session state isolation.

The higher ready RSS delta is 0.41 MiB per session when divided across ten sessions. The substantially lower post-close residual is favorable, but one local process sample is not sufficient to establish long-term leak behavior. The result passes the requested ten-session gate.

## Performance acceptance

PASS.

The repair did not trade correctness for timing. It removed the lifecycle race, preserved exact data and session isolation, improved warm first-useful time, stale first-useful time, grid and filter settlement, drawer summary readiness, reactive settlement, and browser long-task behavior. Slower cold HTTP, stale HTTP, and navigation samples are disclosed and remain within usable local behavior.

Primary evidence:

- `artifacts/shiny-1.7-audit/before/performance/metrics.json`
- `artifacts/shiny-1.7-audit/after/performance/metrics.json`
- `artifacts/shiny-1.7-audit/before/warm-runtime/runtime/runtime-metrics.json`
- `artifacts/shiny-1.7-audit/after/runtime/runtime-metrics.json`
- `artifacts/shiny-1.7-audit/after/e2e/final-full-e2e.log`
- `artifacts/shiny-1.7-audit/after/rapid-repetitions/summary.json`
