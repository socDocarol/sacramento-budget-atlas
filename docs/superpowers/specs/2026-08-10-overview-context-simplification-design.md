# Overview Context Simplification Design

**Date:** 2026-08-10
**Status:** Approved for implementation planning

## Purpose

Simplify the Budget Atlas opening and Overview controls so City managers and
City staff can immediately understand the selected budget measure, year, and
fund scope. Remove controls and labels that repeat state, obscure the chart's
interactive behavior, or imply unsupported fiscal meaning.

The source contains approved budget records classified as revenues or
expenses. The interface must never add those two measures into a single dollar
metric or describe the result as approved authority.

## Design principles

- Present approved expenses and approved revenue estimates as separate
  measures.
- Do not imply actual expenditures, actual receipts, surplus, deficit,
  available balance, performance, or service outcomes.
- Prefer direct terms such as `change` over abstract terms such as `movement`.
- Let existing elements carry interaction state instead of adding explanatory
  rows, banners, or badges.
- Preserve the existing four-card KPI footprint while making it easier to scan.
- Keep the protected navigation bar and footer unchanged.

## Fixed opening benchmark

Replace the combined FY2027 approved-authority headline with a fixed expense
benchmark:

- Label: `FY2027 Citywide Approved Expenses`
- Value: `$1,599,421,675` for the currently prepared FY2027 snapshot
- Supporting copy: `All funds approved spending plan | Not actual expenditures`

The benchmark remains fixed when the analytical year, measure, or fund scope
changes. It provides a consistent reference point rather than duplicating the
active analytical context. The implementation should derive and format the
value from the prepared snapshot rather than retain a hard-coded total when a
reliable bundle is available.

The disclaimer appears here once. Remove the duplicate `Values are approved
budgets, not actual spending.` sentence from the control area.

## Citywide Context header

Keep `CITYWIDE CONTEXT` aligned left. Remove `Approved authority` from the
right-hand metadata. Show only the active fiscal year, such as `FY2027`, flush
right. When a user selects another year through the chart, update this label to
that year.

## Controls

Remove the following controls and state summaries:

- Fiscal Year dropdown
- Compare With dropdown
- Budget Flow dropdown
- Large Reset View button
- Adjacent approved-budget disclaimer
- `Active context` label
- Fiscal-year context pill
- Comparison-year context pill
- Revenue-and-expenses context pill
- Fund-scope context pill

Retain the Fund Scope dropdown. Add a compact but noticeable reset icon at the
right edge of the control row. The reset action restores:

- FY2027
- Expenses
- All funds

The icon must have an accessible name of `Reset to FY2027 expenses and all
funds`, a visible keyboard-focus state, and a hover or focus tooltip. It must be
large enough to discover without recreating the visual weight of the removed
button.

The analytical comparison year is always the immediately preceding fiscal
year. It is no longer independently selectable.

## KPI grid and measure selection

Preserve the existing two-by-two KPI grid. Increase card height and improve
vertical spacing. Increase the prominence of KPI labels, including `APPROVED
REVENUE` and `APPROVED EXPENSES`. Show complete comma-separated dollar values
instead of abbreviated `M` or `B` values.

### Top row

The top cards display both sides of the selected year's budget and also act as
the measure selector.

1. **Approved Revenue**
   - Full approved revenue estimate for the active year and fund scope
   - Supporting copy: `FY2027 approved revenue estimate`, with the year updated
     from chart selection

2. **Approved Expenses**
   - Full approved expense amount for the active year and fund scope
   - Supporting copy: `FY2027 approved spending plan`, with the year updated
     from chart selection

Expenses is selected by default. Selecting either card updates the analytical
charts and both lower KPI cards. The selected card must be unmistakable through
a stronger border, a modest background treatment, and clear hover and focus
states. A compact `Viewing` indication may appear inside the selected card, but
it must not add a new row or separate control.

Both cards must be semantic buttons, keyboard operable, and expose their
pressed state to assistive technology. Their selected treatment must not rely
on color alone.

No combined revenue-and-expenses view or total remains in the Overview.

### Bottom row

The bottom cards respond to the selected measure, active chart year, and fund
scope.

3. **Change from prior fiscal year**
   - Primary value: full signed dollar change, for example `+$84,321,004`
   - Supporting copy: signed percentage change and explicit comparison year,
     for example `+5.6% from FY2026`
   - If the prior value is zero, do not calculate a percentage; describe the
     amount as new in the selected year.

4. **Largest Department**
   - Primary value: department name
   - Supporting copy: full approved amount and its share of the selected
     measure, for example `$272,808,876 | 17.1% of approved expenses`
   - Calculate within the active year, selected measure, and fund scope.

Replace the existing Net Position and Budget Rows cards. A simple revenue less
expenses value is not evidence of surplus, deficit, or available fund balance,
and source-row count is technical metadata rather than an executive KPI.

## Chart-driven year selection

FY2027 is the initial analytical year. The historical bar chart becomes the
only year selector.

- Add readable fiscal-year labels to the x-axis.
- Give bars an obvious hover treatment and pointer cursor.
- Highlight the selected year persistently.
- Provide an interaction cue such as `View FY2025 details` in the bar's
  accessible name or tooltip.
- Support keyboard selection of years or provide an equivalent accessible
  interaction that does not require pointer use.
- When a year is selected, update the Citywide Context year, both top KPI
  values, both lower KPI values, the selected bar, and the chart caption.

The selected measure and fund scope remain active when the year changes.

## Chart caption

Use a smaller and more subdued caption below the chart. Separate the current
amount and comparison with a vertical bar:

`FY2027: $1,599,421,675 | Change from FY2026: +$84,321,004 (+5.6%)`

The caption always describes the selected measure and active fund scope. Use
the immediately preceding year. Handle missing prior-year data explicitly
instead of displaying a misleading zero or percentage.

## Terminology changes

Remove user-visible use of `movement` and `movements` throughout the
application. Replace each occurrence contextually with `change` or `changes`.
In particular:

- `Largest Department Movements` becomes `Largest Department Changes`.
- References to overall movement become overall change.
- Chart titles, captions, instructions, tooltips, empty states, and accessible
  labels receive the same terminology review.

Do not perform a blind replacement that creates awkward grammar. Internal
identifiers may remain unchanged when renaming them would create unrelated
refactoring or migration risk.

## Spacing and responsive behavior

Make restrained layout adjustments after removing controls and the Active
Context row:

- Close the unused vertical space without crowding the KPI grid.
- Preserve a clear visual boundary between the Fund Scope control, KPIs, and
  charts.
- Keep the existing four-card desktop grid.
- Stack cards in the established responsive order at narrow widths.
- Ensure full raw values wrap or scale safely without clipping or horizontal
  overflow.
- Preserve the existing navigation, footer, focus visibility, and semantic
  landmarks.

Do not introduce new banners, explanatory rows, or persistent UI elements.

## Data and interpretation rules

- Revenue and expense totals must be calculated separately from source rows.
- Revenue labels must describe an approved estimate, not revenue authority or
  actual receipts.
- Expense labels must describe the approved spending plan, not actual
  expenditures.
- The fixed opening benchmark uses all-funds FY2027 expenses.
- Active KPI calculations use the selected year and fund scope.
- Prior-year comparisons use the same measure and fund scope as the active
  value.
- All displayed totals must reconcile to the existing prepared-bundle
  aggregates and supporting source rows.

## Validation requirements

Implementation validation must cover:

- Separate and reconciled revenue and expense totals
- No combined revenue-plus-expense dollar metric
- Default state of FY2027, Expenses, and All funds
- Revenue and Expenses KPI-card selection with mouse and keyboard
- Correct pressed and focus states for assistive technology
- Chart-driven year selection and immediately preceding-year comparison
- Fund Scope filtering across all four KPI cards and the chart caption
- Reset icon behavior and accessible name
- Zero or missing prior-year comparison handling
- Full-value formatting at desktop and responsive widths
- No horizontal overflow or clipped values
- No remaining user-visible `movement` or `movements` wording
- Unchanged protected navigation and footer behavior

Visual verification should follow the repository guidance at 2048, 1440, and
800 CSS pixel widths when local tooling permits.

## Out of scope

- Adding actual expenditure or actual revenue data
- Inferring surplus, deficit, fund balance, efficiency, or performance
- Changing the source-data contract or prepared-cache architecture
- Changing navigation or footer content and styling
- Adding new filters or KPI cards
- Azure infrastructure or deployment changes
