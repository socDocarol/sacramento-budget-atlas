# Sacramento Budget Atlas graphic standards

This document translates the City of Sacramento identity rules into practical
standards for the Sacramento Budget Atlas. It also separates official City
requirements from application-specific design choices.

## Authority and reference order

Use this order when sources appear to conflict:

1. `AGENTS.md` for protected application surfaces and change procedure.
2. `docs/standards/City-of-Sacramento-Graphic-Standards.pdf` for official City
   identity requirements.
3. This document for applying those requirements to the Atlas.
4. `docs/brand-translation.md` for the existing digital palette and type
   translation.
5. `docs/creative-direction.md` for page composition and visual storytelling.
6. The current verified application render for implementation details.

The included City manual is dated March 2013 and shows a February 2014 review
date. Its identity rules are the controlling local reference, but its contact
details and administrative process may be outdated. Confirm current approval
requirements with the City's communications staff before any public release.

The included PDF has SHA-256:

`355E288F8BC54D60D74E6676AD56C0128D47BAB26A0A6768AD1582952C77AE82`

## Official City identity

### Signature artwork

- Use the supplied `www/assets/COStreatmentBLUE.png` artwork.
- Do not recreate the signature with text.
- Do not recolor, crop, rearrange, distort, rotate, stretch, or animate its
  internal elements.
- Preserve its aspect ratio and original relationship of the signature
  elements.
- Maintain clear space around the signature. The official manual defines the
  minimum by the height of the letter S in Sacramento. The Atlas uses at least
  16 CSS pixels as its practical minimum.
- Keep the signature at least one inch wide. The Atlas uses at least 160 CSS
  pixels on desktop as a conservative digital mapping.
- Keep the application title separate from the City signature.
- Do not substitute the City seal. The seal is not an application logo.

### Official identity colors

| Name | Digital value | Official reference |
| --- | --- | --- |
| Cobalt | `#2A3B66`, RGB 42, 59, 102 | Pantone 2758 C |
| Slate | `#76AFDF`, RGB 118, 175, 223 | Pantone 284 C |
| Feather gold | `#E9C791`, RGB 233, 199, 145 | Pantone 7509 C |

These three colors are official identity anchors. Do not imply that the
application colors below are additions to the City identity system.

### Official signature typography

The manual identifies Gill Sans Pro Light and Garamond Premier Pro Display
Light Italic as parts of the signature. The Atlas does not recreate the
signature with those or substitute fonts. It uses the supplied image artwork.

## Atlas application system

### Application colors

| Role | Value | Use |
| --- | --- | --- |
| River ink | `#10233F` | Primary text and deep data emphasis |
| Paper | `#F6F3EC` | Editorial background |
| Mist | `#DDEBF2` | Supporting fields and chart structure |
| Cypress | `#24645B` | Secondary semantic emphasis |
| Coral warning | `#B95045` | Warnings and exceptional states |
| White | `#FFFFFF` | Surfaces and reverse contrast |

Use color to express hierarchy and data meaning. Maintain text and interactive
contrast appropriate to WCAG AA. Never depend on color alone to communicate a
selection, warning, increase, or decrease.

### Application typography

- Use Inter for interface labels, controls, navigation, tables, and financial
  values.
- Use Georgia only for a limited editorial voice, such as the primary overview
  headline.
- Use stable, explicit sizes inside compact panels. Do not scale type directly
  with viewport width.
- Keep letter spacing at zero for normal reading text. Modest positive spacing
  is acceptable for short uppercase labels.
- Prevent headings, control labels, and values from touching or escaping their
  containers.

### Photography and decorative assets

- Use high-quality, welcoming, professional images with clear civic relevance.
- Keep documentary City photographs recognizable and appropriately framed.
- Do not enlarge an image beyond a resolution that remains visually clean.
- Use generated art only as a supporting decorative layer. It must not suggest
  a real City building, person, seal, decision, or data record.
- Decorative imagery must remain subtle enough for charts and text to stay
  legible.
- Hide purely decorative images from assistive technology.
- Record the source, retrieval date, local usage basis, and limitations of each
  asset in `docs/asset-provenance.md`.

## Protected application shell

The current navigation bar and footer are approved project baselines. Their
content, spacing, alignment, and behavior must not change during ordinary
content work.

### Navigation baseline

- Sticky 80 pixel header.
- Maximum 120rem shared grid with 24 pixel desktop gutters.
- Portal link, City identity, and navigation share one vertical center at 40
  pixels.
- `Return to portal` is the first item at the grid's left edge.
- City identity follows it with a 16 pixel visual gap.
- City signature is 52 pixels high on desktop.
- Approved Budget identity remains adjacent to the signature.
- Primary navigation aligns to the grid's right edge.
- Existing responsive navigation, link order, labels, targets, active states,
  and focus states remain intact.

### Footer baseline

- Full-width cobalt band.
- Centered white panel containing the unmodified City signature.
- Current source and methodology statement.
- Current snapshot and refresh metadata.
- Existing responsive stacking, link targets, accessible text, and focus
  behavior.

The owning implementation surfaces are `budget_app/ui/shell.py`, the shell
rules in `www/city.css`, and shell behavior in `www/app.js`.

## Main-content composition

- Use the available horizontal space without making the page edge-to-edge.
- Keep a 120rem maximum content width, at least 24 pixel desktop gutters, and
  approximately 40 pixel interior insets for major analytical regions.
- Favor a visible overview with analysis already present. Do not require
  unnecessary clicks before users can understand the budget.
- Pair related modules side by side when the viewport permits it.
- Keep repeated cards at 8 pixel radius or less.
- Do not nest decorative cards inside cards.
- Give all text and controls enough internal padding.
- Use stable dimensions for charts, grids, counters, and fixed-format controls
  so loading or interaction does not shift the layout.
- Preserve a clear visual path from citywide context to department detail and
  exact records.
- Keep all analysis explicit that values are approved authority, not actual
  spending.

## Accessibility and responsive behavior

- Preserve semantic landmarks and a single main landmark.
- Preserve the skip link, accessible navigation names, image alternative text,
  focus visibility, and keyboard operation.
- Ensure controls have usable labels and state is not communicated by color
  alone.
- Avoid text clipping, content overlap, and horizontal page overflow.
- Maintain readable line lengths and sufficient padding on desktop and
  responsive layouts.
- Validate the visible interface in Microsoft Edge or Chromium. A passing unit
  test does not override a reported browser-visible regression.

## Change evidence

For ordinary main-content changes:

1. Inspect the current render before editing.
2. Make a focused change in the owning component or style rule.
3. Run the required narrow smoke gate.
4. Inspect desktop and responsive renders for overflow, clipping, console
   errors, keyboard regressions, and protected-shell movement.
5. Update documentation or provenance when applicable.

For an explicitly requested navigation or footer change, also capture before
and after screenshots, record measured alignment and dimensions, and confirm
that every unrelated shell detail remains unchanged.

