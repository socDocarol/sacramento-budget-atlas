# Azure Deployment Explainer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained HTML explainer that makes Budget Atlas authentication, GitHub Actions, OIDC, Azure Container Apps deployment, approvals, and failure behavior understandable to a non-specialist.

**Architecture:** One semantic HTML document owns the content and visual system. Embedded CSS creates the diagrams, responsive layouts, print treatment, and visible focus states; native `<details>` elements provide optional depth without JavaScript. A focused pytest contract verifies the required sections, source-evidence labels, safety boundaries, and offline-only implementation.

**Tech Stack:** HTML5, embedded CSS, Python 3.12, pytest, Playwright browser tooling for manual visual inspection

## Global Constraints

- Create `docs/azure-deployment-explainer.html` as one self-contained HTML file.
- Use embedded CSS and no JavaScript.
- Load no external assets, libraries, fonts, analytics, or network resources.
- Use a calm City-aligned palette, high contrast, system fonts, cards, arrows, badges, and a compact legend.
- Keep the complete reading order logical if CSS is unavailable.
- Support keyboard navigation, 390 CSS pixel screens, desktop screens, and printing.
- Do not include Azure subscription IDs, tenant IDs, application client IDs, principal IDs, access tokens, registry credentials, client secrets, or employee-specific private data.
- Distinguish direct CLI evidence from recommendations and inference.
- State that the exact Measure U workflow YAML was not available to the current GitHub account.
- Do not use em dash characters.

## File Structure

- Create `docs/azure-deployment-explainer.html`: the complete visual explainer and its embedded styles.
- Create `tests/test_azure_deployment_explainer.py`: the durable content, accessibility, privacy, and offline-asset contract.

---

### Task 1: Encode the explainer contract and build the page

**Files:**
- Create: `tests/test_azure_deployment_explainer.py`
- Create: `docs/azure-deployment-explainer.html`

**Interfaces:**
- Consumes: the approved design in `docs/superpowers/specs/2026-08-09-azure-deployment-explainer-design.md`, the deployment sequence in `.github/workflows/deploy-azure-demo.yml`, and the identity and runtime controls in `infra/app.bicep` and `infra/modules/platform.bicep`.
- Produces: a static page with section IDs `identity-overview`, `two-lanes`, `oidc`, `setup-vs-release`, `measure-u-comparison`, `approval-map`, `deploy-walkthrough`, and `next-request`; eight elements carrying `data-deploy-step="1"` through `data-deploy-step="8"`; evidence badges using `data-evidence="direct"`, `data-evidence="recommended"`, and `data-evidence="inference"`.

- [ ] **Step 1: Write the failing structural and safety tests**

Create `tests/test_azure_deployment_explainer.py` with this complete contract:

```python
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPLAINER = ROOT / "docs" / "azure-deployment-explainer.html"
REQUIRED_SECTIONS = {
    "identity-overview",
    "two-lanes",
    "oidc",
    "setup-vs-release",
    "measure-u-comparison",
    "approval-map",
    "deploy-walkthrough",
    "next-request",
}


class ExplainerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.section_ids: set[str] = set()
        self.evidence_kinds: set[str] = set()
        self.deploy_steps: list[str] = []
        self.tags: list[str] = []
        self.external_references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        values = dict(attrs)
        if tag == "section" and values.get("id"):
            self.section_ids.add(values["id"])
        if values.get("data-evidence"):
            self.evidence_kinds.add(values["data-evidence"])
        if values.get("data-deploy-step"):
            self.deploy_steps.append(values["data-deploy-step"])
        for name in ("href", "src"):
            value = values.get(name, "") or ""
            if value.startswith(("http://", "https://", "//")):
                self.external_references.append(value)


def _page() -> tuple[str, ExplainerParser]:
    html = EXPLAINER.read_text(encoding="utf-8")
    parser = ExplainerParser()
    parser.feed(html)
    return html, parser


def test_explainer_has_every_required_section_and_deployment_step() -> None:
    html, parser = _page()

    assert REQUIRED_SECTIONS <= parser.section_ids
    assert parser.deploy_steps == [str(step) for step in range(1, 9)]
    assert parser.evidence_kinds == {"direct", "recommended", "inference"}
    assert "People use Microsoft Entra to enter the app" in html
    assert "No reusable Azure password is saved in GitHub" in html
    assert "the exact Measure U workflow YAML was not available" in html


def test_explainer_is_offline_semantic_and_javascript_free() -> None:
    html, parser = _page()

    assert '<html lang="en">' in html
    assert "main" in parser.tags
    assert "nav" in parser.tags
    assert "details" in parser.tags
    assert "table" in parser.tags
    assert "script" not in parser.tags
    assert parser.external_references == []
    assert "@media (max-width: 720px)" in html
    assert "@media print" in html
    assert ":focus-visible" in html


def test_explainer_contains_no_identifiers_secrets_or_unresolved_markers() -> None:
    html, _ = _page()

    forbidden_literals = {
        "AZURE_CLIENT_ID",
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "client-secret",
        "PLACE" + "HOLDER",
        "T" + "BD",
        "TO" + "DO",
        chr(0x2014),
    }
    assert forbidden_literals.isdisjoint(html)
    assert re.search(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        html,
    ) is None
```

- [ ] **Step 2: Run the focused test and verify it fails because the page does not exist**

Run:

```powershell
uv run --frozen pytest tests/test_azure_deployment_explainer.py -q
```

Expected: FAIL with `FileNotFoundError` for `docs/azure-deployment-explainer.html`.

- [ ] **Step 3: Implement the semantic document and embedded visual system**

Create `docs/azure-deployment-explainer.html` with this exact semantic order:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>How Budget Atlas Gets to Azure</title>
  <style>/* Complete embedded responsive and print styles described below. */</style>
</head>
<body>
  <header class="hero">
    <p class="eyebrow">Sacramento Budget Atlas</p>
    <h1>How Budget Atlas gets to Azure</h1>
    <p class="lede">People use Microsoft Entra to enter the app; GitHub uses OIDC to update the app; the running app uses a separate runtime identity to retrieve its container image.</p>
  </header>
  <nav aria-label="Explainer sections">
    <a href="#identity-overview">Three identities</a>
    <a href="#two-lanes">Two workflows</a>
    <a href="#oidc">OIDC</a>
    <a href="#setup-vs-release">Setup vs release</a>
    <a href="#measure-u-comparison">Measure U comparison</a>
    <a href="#approval-map">Approvals</a>
    <a href="#deploy-walkthrough">Deploy walkthrough</a>
    <a href="#next-request">Next request</a>
  </nav>
  <main>
    <section id="identity-overview"><h2>Three identities, three different jobs</h2><p>The employee badge, deployment robot, and runtime key are not interchangeable.</p></section>
    <section id="two-lanes"><h2>Two workflows that never share a login</h2><p>One lane admits employees; the other safely releases code.</p></section>
    <section id="oidc"><h2>OIDC is a temporary verified badge</h2><p>GitHub proves which approved workflow is asking Azure for short-lived access.</p></section>
    <section id="setup-vs-release"><h2>One-time setup versus a routine release</h2><p>Administrators establish the boundaries once; routine releases operate inside them.</p></section>
    <section id="measure-u-comparison"><h2>What Measure U proves, and what Budget Atlas should change</h2><p>Shared infrastructure can be reused while each repository keeps separate identities and access controls.</p></section>
    <section id="approval-map"><h2>Who approves what</h2><p>Approval follows the resource boundary, not one universal administrator role.</p></section>
    <section id="deploy-walkthrough"><h2>What happens when I press deploy?</h2><p>Eight guarded steps move one tested image from GitHub to Azure.</p></section>
    <section id="next-request"><h2>The next conversation</h2><p>Ask the DBA platform owner to approve shared-platform reuse and identify the scoped RBAC approver.</p></section>
  </main>
  <footer><p>This explainer contains resource names and workflow concepts, but no tenant, subscription, principal, credential, or employee-private identifiers.</p></footer>
</body>
</html>
```

Use CSS custom properties with these roles: `--ink`, `--muted`, `--paper`, `--panel`, `--city-blue`, `--city-blue-dark`, `--aqua`, `--gold`, `--green`, `--red`, `--line`, and `--shadow`. Use a system font stack. Use CSS Grid for identity cards, comparison cards, and setup versus release; switch every multi-column grid to one column inside `@media (max-width: 720px)`. Use borders and text labels in addition to color. Provide `:focus-visible` outlines. In `@media print`, remove shadows, expand `<details>`, preserve borders, avoid breaking cards, hide the navigation, and use white backgrounds.

The visible copy must include:

- The summary: "People use Microsoft Entra to enter the app; GitHub uses OIDC to update the app; the running app uses a separate runtime identity to retrieve its container image."
- Three non-interchangeable identity cards named "Employee badge", "Deployment robot", and "Runtime key".
- Employee lane: Employee browser, Microsoft Entra sign-in, Budget Atlas access group check, Budget Atlas.
- Deployment lane: Developer starts the workflow, quality and security checks, GitHub OIDC proof, Azure deployment identity, container registry, Container App update.
- OIDC steps: GitHub presents a temporary signed badge; Azure checks repository and approved deployment context; Azure issues a short-lived token; Azure RBAC limits allowed changes; "No reusable Azure password is saved in GitHub."
- One-time setup: shared-platform approval, repository-specific deployment identity, federated credential, scoped role assignments, Entra application, employee access group, and protected GitHub environment.
- Routine release: choose a commit, run tests and formatting, build one immutable image, create SBOM, scan the exact image, exchange OIDC proof, push by digest, update the app, and wait for health probes.
- Measure U direct evidence: shared `saccity-shared-env`, shared `saccitydaoregistry`, repository and `main`-branch-bound federated identity, broad deployment permissions on shared resources, registry admin enabled, registry password secret, and Container Apps authentication disabled.
- Budget Atlas recommendation: reuse shared environment, registry, and logging; create repository-specific deployment identity; create separate runtime pull identity; enable Entra authentication and access-group assignment; scale from zero to one.
- Inference disclaimer using the exact phrase "the exact Measure U workflow YAML was not available" and stating that individual commands were not inspected.
- Approval table rows for platform reuse, deployment identity creation, Azure role assignment, employee login application, employee access assignment, group membership, and routine GitHub release approval.
- Eight numbered deployment cards matching `.github/workflows/deploy-azure-demo.yml`: checkout; Python quality and tests; immutable image build; SBOM and vulnerability scan; OIDC request; registry push and digest resolution; Container App revision update; health polling and traffic protection.
- Failure callouts: tests stop before Azure login; a vulnerability gate stops before upload; unhealthy or timed-out revision leaves the prior single revision serving traffic.
- Copy-ready request: "Can Budget Atlas reuse saccity-shared-env and saccitydaoregistry with a new repository-specific GitHub OIDC identity? If so, can you assign its ACR and Container Apps roles, or identify the DBA RBAC owner?"

Use native `<details>` blocks for exact GitHub/Azure terminology, the distinction between OIDC and employee sign-in, the Measure U evidence limitation, and why the identities are separated. Add `aria-label` only where native headings or table captions do not already provide a clear accessible name.

- [ ] **Step 4: Run the focused test and fix only contract failures**

Run:

```powershell
uv run --frozen pytest tests/test_azure_deployment_explainer.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Run repository formatting and the complete non-live test suite**

Run:

```powershell
uv run --frozen ruff check --no-cache tests/test_azure_deployment_explainer.py
uv run --frozen ruff format --check --no-cache tests/test_azure_deployment_explainer.py
uv run --frozen pytest -p no:cacheprovider
```

Expected: Ruff reports no errors and the full suite passes.

- [ ] **Step 6: Commit the tested explainer**

```powershell
git add -- docs/azure-deployment-explainer.html tests/test_azure_deployment_explainer.py
git commit -m "docs: add Azure deployment visual explainer"
```

### Task 2: Verify responsive, accessible, and print presentation

**Files:**
- Modify if inspection reveals a defect: `docs/azure-deployment-explainer.html`
- Test: `tests/test_azure_deployment_explainer.py`

**Interfaces:**
- Consumes: the section IDs and evidence labels produced by Task 1.
- Produces: browser screenshots at 1440 by 1200 and 390 by 844, plus a visually inspected print rendering with no clipping or horizontal overflow.

- [ ] **Step 1: Serve the repository over localhost**

Run in a dedicated terminal:

```powershell
uv run python -m http.server 8765 --bind 127.0.0.1
```

Expected: the explainer is available at `http://127.0.0.1:8765/docs/azure-deployment-explainer.html` without loading external requests.

- [ ] **Step 2: Capture desktop and mobile screenshots with Playwright**

Run this temporary in-memory inspection command without creating another project file:

```powershell
uv run python -c "from pathlib import Path; from playwright.sync_api import sync_playwright; out=Path('.cache/azure-explainer-qa'); out.mkdir(parents=True, exist_ok=True); p=sync_playwright().start(); b=p.chromium.launch(); d=b.new_page(viewport={'width':1440,'height':1200}); d.goto('http://127.0.0.1:8765/docs/azure-deployment-explainer.html'); d.screenshot(path=str(out/'desktop.png'), full_page=True); m=b.new_page(viewport={'width':390,'height':844}); m.goto('http://127.0.0.1:8765/docs/azure-deployment-explainer.html'); m.screenshot(path=str(out/'mobile.png'), full_page=True); print({'desktop_overflow': d.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth'), 'mobile_overflow': m.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth')}); b.close(); p.stop()"
```

Expected: both overflow values are `False` and both PNG files exist under `.cache/azure-explainer-qa/`.

- [ ] **Step 3: Inspect both screenshots and the browser reading order**

Check that the headline and summary are understandable before scrolling, identity types are visually distinct, both lanes read left to right on desktop and top to bottom on mobile, evidence badges remain attached to their claims, the approval table remains readable at 390 pixels, and every deployment card has a visible number and failure state where applicable.

Expected: no clipped text, overlapping elements, isolated arrow labels, unreadably small type, or visual dependence on color alone.

- [ ] **Step 4: Inspect print output**

Open the browser print preview for the explainer and select a portrait PDF destination. Confirm the navigation is hidden, details content is visible, card borders remain visible, and headings or cards are not stranded or clipped across pages.

Expected: a logical portrait reading order with no horizontal clipping.

- [ ] **Step 5: Apply and test any visual corrections**

If inspection found a defect, edit only the relevant CSS or semantic markup in `docs/azure-deployment-explainer.html`, then rerun:

```powershell
uv run --frozen pytest tests/test_azure_deployment_explainer.py -q
uv run --frozen ruff check --no-cache tests/test_azure_deployment_explainer.py
uv run --frozen ruff format --check --no-cache tests/test_azure_deployment_explainer.py
```

Expected: all focused checks pass after the visual correction.

- [ ] **Step 6: Scan the final artifact for prohibited content**

Run:

```powershell
$file = 'docs/azure-deployment-explainer.html'
$patterns = @('AZURE_CLIENT_ID', 'AZURE_TENANT_ID', 'AZURE_SUBSCRIPTION_ID', 'client-secret', ('PLACE' + 'HOLDER'), ('T' + 'BD'), ('TO' + 'DO'), ([char]0x2014), 'https?://')
$hits = Select-String -LiteralPath $file -Pattern ($patterns -join '|') -CaseSensitive:$false
if ($hits) { $hits; exit 1 }
git diff --check
```

Expected: no matches and no whitespace errors.

- [ ] **Step 7: Commit visual corrections if the inspection required changes**

```powershell
git add -- docs/azure-deployment-explainer.html tests/test_azure_deployment_explainer.py
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) { git commit -m "docs: refine Azure explainer presentation" }
```

Expected: either no new commit is needed or the visual-only correction commit succeeds.
