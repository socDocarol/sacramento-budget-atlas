# Demo status

Date: July 29, 2026

Status: Demo-ready local proof of concept

## Implemented

- Standalone Shiny for Python 1.7 application copied from the certified Budget
  source.
- Prepared bundle `v1-d3894619890346c9` retained as the startup source.
- Original Budget Shiny header, footer, navigation, analytical modules,
  utility actions, drilldowns, Explorer, and share-state behavior retained.
- Unified Civic Budget Story Studio stage combining narrative and live
  analysis horizontally.
- Official Sacramento Historic City Hall and City Council chambers images.
- Two generated decorative asset families used as a cohesive, restrained
  background treatment.
- Expanded City Hall and City Council chambers photography.
- Equal-width, equal-height movement and fund-scope analysis panels.
- FY2027 approved authority and its approved-authority limitation visible on
  load.
- Long-value containment applied to live cards and the detail drawer.
- Background source refresh disabled for deterministic meeting use.

## Required smoke result

The corrected path ran against `http://127.0.0.1:8125/`:

- Focused component and asset gate: 3 passed
- Browser engine: Microsoft Edge
- Browser widths: 2048 by 1152, 1440 by 900, and 1100 by 800
- Versioned stylesheet loaded: `city.css?v=20260729l`
- Story Studio assets loaded: 4 of 4
- Live Overview KPI cards in the combined stage: 4
- Combined stage width at 2048: 1872px
- Combined stage width at 1440: 1392px
- Story Studio interior inset: 40px
- City Hall image height: 256px
- City Council chambers image height: 192px
- Lower movement panel at 2048: 902px by 739px
- Lower fund-scope panel at 2048: 902px by 739px
- Fund-scope display value size: 32px
- Full Return to portal label aligned to the Story container
- City branding follows the portal link with a 16px gap
- Navigation aligns to the Story container's right edge
- Portal, City branding, and navigation share the 40px header centerline
- City logo height: 52px
- Header portal and brand overlap: none
- Header brand and navigation align to the 120rem Story grid
- Detail surface heading inset: 16px
- Lower panels stack at 1100px
- Signed movement bars: 6
- Page horizontal overflow: none
- Browser console and page errors: 0

Evidence:

- `artifacts/polish-accepted-2048x1152.png`
- `artifacts/polish-accepted-delayed-1440x900.png`
- `artifacts/polish-accepted-summary-2048x1152.png`
- `artifacts/polish-accepted-summary-1440x900.png`
- `artifacts/polish-accepted-1100x800.png`
- `artifacts/atlas-polish-server.err.log`

## Known limitations

- This is a rapid desktop demo, not a production release.
- City data-owner and communications approvals have not occurred.
- City photography is local POC use pending permission confirmation.
- Comprehensive accessibility, browser, load, stale-cache, and lifecycle
  matrices remain outside the Rapid Demo Directive.

## Post-meeting backlog

- Conduct the user-led visual and interaction review.
- Correct issues reported from the meeting path.
- Confirm photography use with the City communications owner.
- Run broader validation only after the demo direction is accepted.
