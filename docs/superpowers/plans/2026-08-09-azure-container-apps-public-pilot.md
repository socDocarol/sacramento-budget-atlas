# Azure Container Apps Public Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt the hardened Azure Container Apps deployment into an anonymously accessible, time-limited Budget Atlas pilot that reuses the DBA shared environment, registry, and logging without changing shared platform configuration.

**Architecture:** Bootstrap only two repository-specific user-assigned identities and their federated/registry role assignments in the existing `DBA` and `Databricks` resource groups. Deploy one new Budget Atlas Container App into the existing `saccity-shared-env` Consumption profile, then scope the GitHub deployment identity to that app so later releases can push and update only immutable image digests. Keep public access anonymous while applying explicit robots exclusion at both the route and response-header layers.

**Tech Stack:** Azure Container Apps Consumption, existing Azure Container Registry Basic, existing Log Analytics integration, Bicep, Azure CLI 2.88 or newer, GitHub Actions OIDC, Docker Buildx, Trivy, Python 3.12, Starlette, Uvicorn, Shiny.

## Global Constraints

- Work only on `feat/azure-container-apps-public-pilot`; preserve `feat/azure-container-apps-demo` and its dirty worktree unchanged.
- Azure subscription: `Microsoft Azure Enterprise - DBA`.
- Container App resource group: `DBA`.
- Existing Container Apps environment: `saccity-shared-env` in resource group `DBA`.
- Existing registry: `saccitydaoregistry` in resource group `Databricks`.
- Do not create or modify a Container Apps environment, registry, Log Analytics workspace, or Measure U resource.
- Use workload profile `Consumption`, `minReplicas: 0`, `maxReplicas: 1`, single revision mode, sticky sessions, HTTPS-only external ingress, and target port `8000`.
- Keep startup and liveness on `/health/live`; keep traffic readiness on `/health/ready`.
- Deploy only an immutable `@sha256:` image reference after tests, SBOM generation, and Trivy scanning pass.
- Use a repository-specific GitHub OIDC identity and a separate runtime identity; grant the runtime identity only `AcrPull` on `saccitydaoregistry`.
- Keep `BUDGET_MANUAL_REFRESH_ENABLED=0`, `SHINY_TESTMODE` unset, and `APP_ALLOWED_HOSTS` equal to the exact Container App FQDN.
- Visitor access is anonymous. Do not create an Entra application, client secret, access group, redirect URI, or Container Apps auth resource.
- Return `X-Robots-Tag: noindex, nofollow` and serve a `robots.txt` that disallows all cooperative crawlers. These controls are guidance, not access control.
- Do not publish the pilot URL in repository documentation.
- Tag pilot-owned Azure resources with `expiresOn: '2026-09-30'` for removal or extension review.

---

### Task 1: Replace dedicated-platform infrastructure with shared-resource identity bootstrap

**Files:**
- Modify: `infra/main.bicep`
- Replace: `infra/modules/platform.bicep` with `infra/modules/identities.bicep`
- Replace: `infra/parameters/demo.bicepparam` with `infra/parameters/public-pilot.bicepparam`
- Test: `tests/test_azure_public_pilot.py`

**Interfaces:**
- Consumes: existing resource groups `DBA` and `Databricks`, environment `saccity-shared-env`, and registry `saccitydaoregistry`.
- Produces: runtime identity ID, GitHub identity client ID/principal ID, registry login server, and existing environment ID/default domain without modifying shared resources.

- [ ] **Step 1: Write failing topology tests**

Assert that the public-pilot parameter file names the DBA subscription resources, the Bicep tree declares the environment and registry as `existing`, only user-assigned identities/federated credentials/role assignments are created, and no Log Analytics, managed environment, registry, resource group, or budget resource is declared.

- [ ] **Step 2: Run the focused tests and verify expected failure**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_azure_public_pilot.py -q`

Expected: FAIL because the hardened templates still create dedicated platform resources and the public-pilot parameter file does not exist.

- [ ] **Step 3: Implement the identity-only bootstrap**

Make `infra/main.bicep` a subscription-scope orchestrator over the existing `DBA` and `Databricks` resource groups; subscription scope is required because deployable role assignments cannot cross a resource-group module boundary. Call `modules/identities.bicep` in `DBA` and `modules/registry-access.bicep` in `Databricks`. Create `id-sac-budget-atlas-runtime-public-pilot` and `id-sac-budget-atlas-github-public-pilot`, create a federated credential with subject `repo:socDocarol/sacramento-budget-atlas:environment:azure-public-pilot`, grant runtime `AcrPull` and GitHub `AcrPush` only on the shared registry, and output exact existing-resource and identity values. The public-pilot parameter file must contain no subscription or tenant IDs and must apply pilot lifecycle tags only to owned identities.

- [ ] **Step 4: Run the focused tests**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_azure_public_pilot.py -q`

Expected: PASS for identity-bootstrap topology tests.

### Task 2: Deploy the anonymous Consumption Container App without an auth resource

**Files:**
- Modify: `infra/app.bicep`
- Replace: `infra/parameters/app-demo.bicepparam` with `infra/parameters/app-public-pilot.bicepparam`
- Test: `tests/test_azure_public_pilot.py`

**Interfaces:**
- Consumes: the exact immutable image digest, existing shared environment/registry, and both pilot identities.
- Produces: `ca-sac-budget-atlas-public-pilot`, its FQDN/revision name, and a GitHub `Container Apps Contributor` assignment scoped to that app resource only.

- [ ] **Step 1: Add failing application-template tests**

Assert `workloadProfileName: 'Consumption'`, anonymous ingress with no `authConfigs` or secret parameters, immutable digest validation, managed-identity registry pull, exact host configuration, scale zero-to-one, sticky single revision mode, three health probes, and app-scoped GitHub deployment RBAC.

- [ ] **Step 2: Run tests and verify expected failure**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_azure_public_pilot.py -q`

Expected: FAIL on the hardened Entra auth and dedicated-resource assumptions.

- [ ] **Step 3: Implement the public-pilot app template**

Reference the shared environment, registry, runtime identity, and GitHub identity as existing resources. Remove Entra parameters, secrets, and `authConfigs`; set `workloadProfileName` explicitly to `Consumption`; retain the hardened runtime/probe/scale contract; and scope the GitHub Container Apps Contributor assignment to the new app resource.

- [ ] **Step 4: Run focused tests and Bicep builds**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_azure_public_pilot.py -q`, `az bicep build --file infra/main.bicep`, and `az bicep build --file infra/app.bicep`.

Expected: all pass with no generated JSON retained in the worktree.

### Task 3: Add application-level indexing exclusion

**Files:**
- Modify: `budget_app/application.py`
- Modify: `tests/test_runtime_hardening.py`

**Interfaces:**
- Consumes: every Starlette response and the root platform route table.
- Produces: `X-Robots-Tag: noindex, nofollow` on responses and `GET /robots.txt` containing `User-agent: *` plus `Disallow: /`.

- [ ] **Step 1: Write failing no-index tests**

Add tests that request `/robots.txt`, `/health/live`, and the app root through the real ASGI application and assert the robots body/content type plus the response header.

- [ ] **Step 2: Run tests and verify expected failure**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_runtime_hardening.py -q`

Expected: FAIL because neither the route nor header exists.

- [ ] **Step 3: Implement the minimal route and middleware**

Add a plain-text robots response before the Shiny mount and add an ASGI middleware that applies `X-Robots-Tag: noindex, nofollow` to all HTTP responses without changing existing security headers.

- [ ] **Step 4: Run focused and full tests**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_runtime_hardening.py -q` and `uv run --frozen pytest -p no:cacheprovider`.

Expected: PASS.

### Task 4: Replace authenticated-demo workflow and operations with the public-pilot route

**Files:**
- Replace: `.github/workflows/deploy-azure-demo.yml` with `.github/workflows/deploy-azure-public-pilot.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/Test-AzureDemoPrerequisites.ps1`
- Modify: `scripts/Test-AzureDemoDeployment.ps1`
- Modify: `scripts/Warm-AzureDemo.ps1`
- Delete: `scripts/Initialize-AzureDemoIdentity.ps1`
- Replace tests: `tests/test_azure_demo_identity.py`, `tests/test_azure_demo_operations.py`, and `tests/test_azure_demo_preflight.py` with public-pilot assertions in `tests/test_azure_public_pilot.py`

**Interfaces:**
- Consumes: protected GitHub environment `azure-public-pilot`, DBA subscription context, existing shared resources, and pilot Container App.
- Produces: build-test-SBOM-scan-OIDC-push-digest-update workflow plus read-only preflight, anonymous smoke test, and warm-up checks.

- [ ] **Step 1: Add failing workflow and operations tests**

Assert the exact shared registry/resource group/app/environment values, deployment environment, OIDC-only permissions, immutable update, anonymous root success, indexing headers, HTTPS, scale, Consumption profile, probe/runtime contract, and explicit checks that shared resources and sibling Container Apps remain untouched.

- [ ] **Step 2: Run tests and verify expected failure**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_azure_public_pilot.py -q`

Expected: FAIL because the hardened workflow and scripts require Entra and the APPS subscription.

- [ ] **Step 3: Implement workflow and operational tooling**

Rename public-facing commands and defaults to the public-pilot resources. Keep workflow build-once, SPDX, Trivy, OIDC, digest resolution, existing-app guard, image-only update, and healthy-revision polling. Make preflight read-only and verify the DBA context, exact shared resource IDs/configuration, Consumption availability, registry state, name collision inventory, and necessary deployment/role-assignment permissions. Make deployment smoke testing require anonymous HTTPS 200, both indexing controls, immutable digest, app-only identity/RBAC expectations, and a real 30-minute Shiny WebSocket session for the active revision.

- [ ] **Step 4: Run focused tests and syntax checks**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_azure_public_pilot.py -q` and PowerShell parser checks for every retained `.ps1` file.

Expected: PASS with no Entra bootstrap or credential references.

### Task 5: Update public-pilot documentation and operator handoff

**Files:**
- Modify: `infra/README.md`
- Modify: `docs/azure-deployment-hardening.md`
- Replace: `docs/azure-container-apps-demo-runbook.md` with `docs/azure-container-apps-public-pilot-runbook.md`
- Modify: `README.md`
- Test: `tests/test_azure_public_pilot.py`

**Interfaces:**
- Consumes: final resource names, preview/deployment commands, and operational verification scripts.
- Produces: a no-URL runbook for preview, bootstrap, first digest deployment, routine GitHub deployment, validation, rollback, scale-to-zero, cost review, and expiry/removal.

- [ ] **Step 1: Add failing documentation assertions**

Assert docs describe anonymous public access, search exclusion limitations, shared-resource non-mutation, exact preview commands, `azure-public-pilot`, narrow RBAC escalation, and the `2026-09-30` review without embedding the environment domain or pilot URL.

- [ ] **Step 2: Run tests and verify expected failure**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_azure_public_pilot.py -q`

Expected: FAIL because hardened docs still describe dedicated infrastructure and employee Entra authentication.

- [ ] **Step 3: Write the operator documentation**

Update the hardening overlay and infrastructure README; replace the demo runbook with the selected public-pilot lifecycle. Preserve the route decision document unchanged as the authoritative handoff and do not publish the resolved default domain.

- [ ] **Step 4: Run documentation tests and repository checks**

Run: `uv run --frozen pytest -p no:cacheprovider tests/test_azure_public_pilot.py -q`, `uv run --frozen ruff check --no-cache .`, `uv run --frozen ruff format --check --no-cache .`, and `git diff --check`.

Expected: PASS with no stale Entra requirements in active public-pilot tooling.

### Task 6: Validate, preview, and attempt the bootstrap

**Files:**
- No planned source changes; record only narrow corrective changes if a validation command exposes a defect.

**Interfaces:**
- Consumes: reviewed Bicep, workflow, scripts, current Azure login, and local Docker runtime/security scanner.
- Produces: full verification evidence or an exact Azure operation/resource-scope/role blocker.

- [ ] **Step 1: Run the complete local quality gate**

Run frozen sync, Ruff lint/format, all default unit tests, Bicep builds, PowerShell parser checks, workflow static assertions, and `git diff --check`.

- [ ] **Step 2: Build and inspect the Docker image**

Build the production Dockerfile once, run the container hardening checks, generate an SPDX SBOM, and scan the exact local image for fixable high/critical OS and library vulnerabilities using Trivy.

- [ ] **Step 3: Run read-only Azure preflight and both deployment previews**

Validate/what-if identity bootstrap in resource group `DBA`, then validate/what-if the app deployment using a syntactically valid placeholder digest only where Azure validation does not pull the image. Inspect change sets to ensure only the two pilot identities, federated credential, scoped role assignments, and new Budget Atlas app are created; no shared environment, registry, logging, or existing app update is allowed.

- [ ] **Step 4: Attempt the identity bootstrap with current permissions**

Run the reviewed bootstrap deployment. If Azure denies it, stop without broadening scope and capture the exact denied operation, exact resource scope, and narrow built-in role or single role assignment required. If it succeeds, continue the documented first-image/app sequence only to the extent authorized by the route and available credentials.

- [ ] **Step 5: Review the branch diff and final state**

Confirm the hardened worktree remains dirty only in its pre-existing explainer/tmp paths, the public-pilot worktree contains only intended changes, and no pilot URL, secret, subscription ID, tenant ID, or generated deployment output was committed.
