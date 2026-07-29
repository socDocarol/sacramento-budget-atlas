# Prepared bundle performance architecture

## Outcome

The application now treats the last complete prepared bundle as the startup source of truth. A valid bundle is opened before a network check, remains usable throughout background refresh, and is replaced only after a complete new version has been written and validated.

The 29,387-row reference snapshot prepared in 645.45 ms, promoted and reopened in 712.45 ms, and reopened from disk in 251.34 ms. The prepared data layer meets the 500 ms availability target. Browser startup remains limited by Shiny widget transport and client rendering, as documented below.

## Bundle contract

`PreparedBudgetBundle` contains read-only normalized rows, persisted `fund_scope`, dimension choices, exact indexes, chart-ready aggregate tables, and validated metadata. The current schema includes:

- Overview totals and totals by fiscal year, flow, and fund scope
- Department, fund, and category hierarchy tables
- Historical series
- Fund-scope totals
- Department signals
- Record counts
- Context-aware choices and exact row indexes

The active reference version is `v1-d3894619890346c9`. Its 13 persisted artifacts total 957,195 bytes.

## Persistence and promotion

The cache layout is:

```text
.cache/
  current.json
  snapshots/
    <version>/
      rows.parquet
      choices.json
      aggregates/
      bundle.metadata.json
```

Preparation writes to a staging location. Promotion reopens the staged bundle, verifies artifact hashes and sizes, validates schema, row count, years, content hash, and reconciliation, then atomically replaces `current.json`. The prior valid version remains available for fallback. Corrupt active bundles fall back to a prior valid version. The legacy Parquet and metadata pair is migrated without deletion.

## Timestamp semantics

`data_updated_at` is the successful source fetch time stored as `fetched_at`. Reading from disk, opening a session, checking unchanged source metadata, and failed refreshes do not alter it.

`checked_at` records the latest source check. `prepared_at` records bundle preparation. A source metadata check that finds no change does not create a new version or invalidate session outputs.

The persistent status shell formats `data_updated_at` in Pacific Time. During refresh it retains the prior timestamp and states that data is updating in the background. Success appears only after validation and atomic promotion. Failure retains the active bundle and timestamp.

## Process coordination

One process-wide `SnapshotStore` owns the active immutable pointer. One `RefreshCoordinator` provides single-flight refresh behavior, performs blocking network and disk work outside the reactive flush, and notifies sessions only when the version changes. The repository reuses one HTTP client for metadata and sequential pages.

Sessions keep independent selection, drawer, and workspace state while sharing immutable prepared data. Hidden What Changed and workspace Plotly widgets are deferred until their view becomes active. Explorer uses a persistent client-side chart host updated with `Plotly.react`; compact chart data crosses the socket without creating a new `FigureWidget`, while chart clicks still return the selected department to Shiny.

## Deterministic measurement

The prepared-cache audit copies `.cache` into an evidence directory, disables background source refresh, and points the source URL at a closed localhost port. It cannot contact ArcGIS.

| Measure | Historical reference | Prepared and lazy widgets | Result |
|---|---:|---:|---|
| Warm restart useful UI | 4,783.53 ms | 3,602.77 ms | 24.7% faster, target not met |
| Warm in-process useful UI | 3,056.95 ms | 2,853.44 ms | 6.7% faster, target not met |
| Explorer first grid | 2,087.96 ms | 272.60 ms | 86.9% faster, target met |
| Explorer filter settlement | 1,686.87 ms | 153.69 ms | 90.9% faster, target met |
| Exercised WebSocket received | 16,621,410 bytes | 6,034,311 bytes | 63.7% reduction |
| Warm in-process WebSocket received | 5,396,894 bytes | 5,396,835 bytes | effectively unchanged |
| Warm DOM mutations | 5,820 | 2,691 | 53.8% reduction |
| Exercised DOM mutations | 5,820 | 6,910 | target not met |
| Longest observed task | 790 to 1,187 ms | 686 to 750 ms | improved, 200 ms target not met |
| Ten-session readiness | 3,478.61 to 17,015.72 ms | 3,867.96 to 13,738.28 ms | 10 of 10, isolated |
| RSS before / ready / closed | 238.8 / 311.1 / 274.7 MB | 274.9 / 318.1 / 304.9 MB | ready RSS 2.3% higher, retained RSS higher |

Chart readiness followed useful Overview by about 13 ms in the exercised first session. The first useful UI and long-task targets remain blocked by the initial Shiny and ipywidgets client stack, including a roughly 3.87 MB widget runtime resource and the remaining Overview FigureWidget payload. Migrating Overview and What Changed to the proven `Plotly.react` contract is the next transport optimization if the startup target is mandatory.

## Validation boundary

Default unit tests exclude both `live` and `e2e` markers. Browser fixtures disable production background refresh unless a stale or failure test explicitly enables a closed-localhost source. The production ArcGIS live test remains opt-in.

This architecture is a single-process pilot. A multi-process deployment requires shared prepared-bundle storage, sticky WebSocket sessions, and either a cross-process refresh lease or a dedicated refresh worker.
