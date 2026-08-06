# Sacramento Budget Atlas Agent Guide

This file applies to the entire repository. It exists to protect the working
demo, its data meaning, and the City identity while still allowing focused
improvements.

## Read before editing

Read these files before making a consequential change:

1. `README.md`
2. `docs/graphic-standards.md`
3. `docs/standards/City-of-Sacramento-Graphic-Standards.pdf`
4. `docs/brand-translation.md`
5. `docs/creative-direction.md`
6. `docs/asset-provenance.md`
7. `docs/data-owner-review.md`

The official PDF governs City identity. `docs/graphic-standards.md` explains
how those rules apply to this application. Existing code and a verified render
are the implementation baseline.

## Highest-priority protected surfaces

The navigation bar and footer must stay the same unless the user explicitly
requests a change to one of them. Do not casually restyle, reorganize, rename,
resize, or replace either surface while working on page content.

Protected implementation surfaces:

- Header and footer markup in `budget_app/ui/shell.py`
- Header and footer selectors in `www/city.css`
- Navigation and shell behavior in `www/app.js`
- City signature artwork at `www/assets/footer-icon.png`

### Navigation bar contract

Preserve all of the following:

- A 64 pixel desktop and 60 pixel mobile sticky header.
- A shared content grid with a maximum width of 120rem and 24 pixel desktop
  gutters.
- `Portal`, preceded by the return arrow, aligned to the left edge of that grid.
- The white City of Sacramento signature and `Budget Dashboard` identity centered as one group.
- A vertical divider and clear spacing between the City signature and application title.
- The City signature rendered at 110 pixels wide on desktop and 84 pixels wide on mobile.
- The visual center of the `Sacramento` wordmark aligned to the title and header control axis.
- Primary navigation aligned to the right edge of the shared grid.
- Portal, centered City identity, and navigation centered on the same vertical axis.
- The header fades and slides away while scrolling down, then returns on upward scroll,
  header focus, or an open navigation menu.
- The existing desktop and mobile navigation labels, order, targets, active
  states, focus behavior, and responsive transition.

The accepted desktop baseline places the center of the portal group, City
identity group, and navigation at 32 pixels from the top of the 64 pixel
header.

### Footer contract

Preserve all of the following:

- The cobalt background band.
- Header and footer shell backgrounds use official cobalt `#2A3B66`.
- The centered white City signature rendered directly on the cobalt band at 210 pixels wide on desktop.
- The current source and methodology wording and links.
- The data snapshot and refresh metadata.
- Existing spacing, responsive behavior, focus behavior, and accessible text.

## Other invariants

- The prepared cached backend and its ArcGIS source contract remain intact.
- Shiny owns filtering, selection, navigation, bookmark, and analytical state.
- Approved budget authority must never be described as actual spending.
- Preserve exact-record drilldown and the supporting source-row path.
- Production snapshot or test-control endpoints must remain unavailable.
  `SHINY_TESTMODE=1` is only for local automated tests.
- Preserve keyboard access, focus visibility, semantic landmarks, and readable
  contrast.
- Do not add an asset without recording its source and usage basis in
  `docs/asset-provenance.md`.
- Do not modify the original Budget source projects from this repository.
- Do not deploy or change repository visibility without explicit user approval.
- Do not use em dash characters in code comments, interface copy, or
  documentation.

## What may change

Future agents may improve the main analytical content when the user requests
it. Appropriate areas include:

- Page composition and spacing below the protected header
- Analytical visualizations and explanatory copy
- Content density and responsive content layouts
- Generated decorative accents
- Main-content accessibility and interaction polish
- Documentation and focused test coverage

Changes must preserve data meaning, source traceability, state behavior,
accessibility, and the visual standards below. Prefer small, isolated edits
over broad CSS overrides.

## How to change the application

1. Inspect the relevant source, current render, and dirty worktree before
   editing.
2. State the intended scope. Treat the header and footer as out of scope unless
   the user named them.
3. Make the smallest coherent change in the owning module.
4. Avoid appending competing CSS overrides. Update the existing owning rule
   when practical and keep the final cascade understandable.
5. When CSS changes, update the cache-busting query in
   `budget_app/application.py`.
6. Preserve the prepared cache. Do not trigger broad refreshes or source
   extraction unless the task requires them.
7. Run the narrow smoke gate appropriate to the change.
8. Inspect the rendered result in Microsoft Edge or Chromium at desktop and
   responsive widths. Browser-visible behavior takes precedence over a passing
   build.
9. Check for horizontal overflow, clipped text, browser console errors,
   keyboard regressions, and em dash characters.
10. Update documentation and asset provenance when the change affects either.

For main-content visual work, use at least 2048, 1440, and 800 CSS pixel wide
viewports when the local tooling permits it. Compare the protected navigation
and footer against the accepted baseline at every inspected width.

## Exception process for the navigation bar or footer

Only change a protected shell surface after an explicit user request. Then:

1. Capture before screenshots and geometry.
2. Identify the exact requested difference.
3. Limit the edit to that difference.
4. Recheck portal, City identity, navigation, active states, keyboard focus,
   mobile behavior, footer links, and footer metadata.
5. Record after screenshots and measured geometry.
6. Confirm that unrelated shell details did not move.

## GitHub boundary

Do not assume a particular GitHub owner, account, organization, or remote.
Contributors may work from a fork.

Before committing or pushing:

1. Inspect `git remote -v`, the current branch, and its upstream.
2. Confirm that the selected remote belongs to the contributor or organization
   that authorized the work.
3. Verify the authenticated GitHub account with
   `gh api user --jq '.login'` when GitHub CLI is used.
4. Use an appropriate repository-local Git identity.
5. Push only to the intended branch and remote.

Preserve the repository's current visibility. Never make a repository public,
transfer it, change its default branch protections, open a pull request against
an upstream project, or deploy the application without explicit approval.
