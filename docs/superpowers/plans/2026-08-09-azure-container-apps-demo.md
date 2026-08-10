# Azure Container Apps Demo Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Sacramento Budget Atlas as a Microsoft Entra-protected Azure Container App that scales to zero, supports one stateful Shiny replica, and normally remains within the Azure Container Apps monthly free grant.

**Architecture:** Provision a dedicated experimental resource group in the City of Sacramento `Microsoft Azure Enterprise - APPS` subscription. A private Basic Azure Container Registry stores immutable images, a Consumption Container Apps environment hosts one scale-to-zero replica, and Log Analytics retains platform logs for 30 days. GitHub Actions authenticates with workload identity federation, pushes an image only after the existing tests and security scan pass, and deploys that exact image digest.

**Tech Stack:** Azure Container Apps Consumption, Azure Container Registry Basic, Log Analytics, Microsoft Entra ID built-in Container Apps authentication, Bicep, Azure CLI 2.88 or newer, GitHub Actions OIDC, Docker Buildx, Trivy, Python 3.12, Uvicorn, Shiny.

## Global Constraints

- This is an internal experimental deployment for team testing and scheduled demonstrations, not a public production service.
- Azure subscription: `Microsoft Azure Enterprise - APPS` in the `City of Sacramento` tenant.
- Azure region: `westus2`.
- Do not register providers, create identities, create resources, change Entra ID, or change GitHub until the relevant deployment task is explicitly approved.
- Use one Container App replica at most and one Uvicorn worker. Do not horizontally scale the current stateful Shiny process.
- Scale configuration is `minReplicas: 0`, `maxReplicas: 1`.
- Initial resource allocation is `0.5` vCPU and `1Gi` memory. Increase memory to `2Gi` before deployment if the profiling gate in Task 2 fails.
- Use ephemeral cache storage at `/var/cache/sacramento-budget` for the first month. Do not create Azure Files, Blob Storage, Key Vault, a VNet, private endpoints, Front Door, Application Gateway, Dapr, Application Insights, or a dedicated workload profile.
- Expect cold starts. Warm the app and confirm `/health/ready` before every scheduled demonstration.
- Use external HTTP ingress on target port `8000`, HTTPS only, single revision mode, and sticky sessions.
- Require Microsoft Entra authentication and explicit assignment to the `Budget Atlas Demo Users` security group before users can access the app.
- Do not enable ACR admin credentials. Use managed identities and Azure RBAC.
- Build once, scan once, push once, and deploy the immutable image digest. Do not deploy `latest`.
- Keep `BUDGET_MANUAL_REFRESH_ENABLED=0` and `SHINY_TESTMODE` unset.
- Keep the source ArcGIS URL on HTTPS and permit outbound HTTPS to that public endpoint.
- Keep Log Analytics retention at 30 days and do not add verbose platform diagnostics during the experiment.
- Review or remove the experimental resources by `2026-09-30`.
- The expected incremental cost is approximately `$5-$10/month`; the Basic ACR is the only predictable fixed charge. A budget is advisory and does not stop resources.

---

## Confirmed Azure State

Read-only Azure CLI inspection on 2026-08-09 established:

- The APPS subscription uses Enterprise Agreement offer `EnterpriseAgreement_2014-09-01`.
- `Microsoft.App` is not registered in APPS.
- APPS has no reusable paid App Service plan, ACR, Container Apps environment, or Log Analytics workspace.
- The DOU P1v3 App Service plan and Shared B1 plan are Windows plans and cannot run this Linux image.
- The DBA Basic registry is owned by a Databricks resource group and has its admin account enabled; it is out of scope for this deployment.
- The current user can inspect resources but cannot read or create City subscription budgets with the present Cost Management permissions.
- No Entra application named `Sacramento Budget Atlas Demo` currently exists.
- No Entra security group named `Budget Atlas Demo Users` currently exists; an identity administrator must create it or approve an existing team group before authentication can be completed.

## Target Resource Inventory

| Resource | Exact name | Configuration |
|---|---|---|
| Resource group | `rg-sac-budget-atlas-demo-wus2` | West US 2; contains only this experiment |
| Log Analytics | `log-sac-budget-atlas-demo-wus2` | `PerGB2018`, 30-day retention |
| Container Apps environment | `cae-sac-budget-atlas-demo-wus2` | Consumption, external Azure-managed ingress |
| Runtime managed identity | `id-sac-budget-atlas-runtime-demo` | `AcrPull` scoped only to the experiment ACR |
| GitHub deployment identity | `id-sac-budget-atlas-github-demo` | OIDC for the `azure-demo` GitHub environment |
| Azure Container Registry | `sacbudgetatlasdemo` | Basic, admin disabled, anonymous pull disabled; CLI confirmed globally available on 2026-08-09 |
| Container App | `ca-sac-budget-atlas-demo` | Single revision, target port 8000, sticky, scale 0-1 |
| ACR repository | `budget-atlas` | Immutable tags formed as `sha-` plus the first 12 lowercase hexadecimal characters of the Git commit, and immutable manifest digests |
| Entra application | `Sacramento Budget Atlas Demo` | Single tenant, ID tokens enabled, assignment required |
| Entra access group | `Budget Atlas Demo Users` | Only assigned team members receive access |
| GitHub environment | `azure-demo` | Manual approval required before deployment |
| Cost budget | `budget-sac-budget-atlas-demo` | `$15` monthly; alerts at 50%, 80%, and 100% |

All resources receive these tags:

```bicep
var tags = {
  workload: 'SacramentoBudgetAtlas'
  environment: 'demo'
  lifecycle: 'experimental'
  owner: 'docarol@cityofsacramento.org'
  dataClassification: 'public-source-internal-app'
  expiresOn: '2026-09-30'
}
```

## Exact Container App Runtime Contract

### Environment variables

| Name | Value |
|---|---|
| `BUDGET_ARCGIS_URL` | `https://services5.arcgis.com/54falWtcpty3V47Z/arcgis/rest/services/City_of_Sacramento_Approved_Budgets/FeatureServer/0` |
| `BUDGET_CACHE_DIR` | `/var/cache/sacramento-budget` |
| `BUDGET_CACHE_TTL_SECONDS` | `86400` |
| `BUDGET_PREPARED_SCHEMA_VERSION` | `1` |
| `BUDGET_BACKGROUND_REFRESH_ENABLED` | `1` |
| `BUDGET_MANUAL_REFRESH_ENABLED` | `0` |
| `BUDGET_MANUAL_REFRESH_COOLDOWN_SECONDS` | `300` |
| `LOG_LEVEL` | `INFO` |
| `APP_BASE_PATH` | `/` |
| `APP_ALLOWED_HOSTS` | `ca-sac-budget-atlas-demo.${containerAppsEnvironment.properties.defaultDomain}` |

`SHINY_TESTMODE` must not be present.

### Ingress and revision settings

```bicep
configuration: {
  activeRevisionsMode: 'Single'
  maxInactiveRevisions: 5
  ingress: {
    external: true
    allowInsecure: false
    targetPort: 8000
    transport: 'auto'
    stickySessions: {
      affinity: 'sticky'
    }
  }
  registries: [
    {
      server: registry.properties.loginServer
      identity: runtimeIdentity.id
    }
  ]
  secrets: [
    {
      name: 'entra-client-secret'
      value: entraClientSecret
    }
  ]
}
```

### Compute, scale, shutdown, and probes

```bicep
template: {
  revisionSuffix: revisionSuffix
  terminationGracePeriodSeconds: 30
  containers: [
    {
      name: 'budget-atlas'
      image: imageDigestReference
      resources: {
        cpu: json('0.5')
        memory: '1Gi'
      }
      probes: [
        {
          type: 'Startup'
          httpGet: {
            path: '/health/live'
            port: 8000
            scheme: 'HTTP'
          }
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 10
        }
        {
          type: 'Liveness'
          httpGet: {
            path: '/health/live'
            port: 8000
            scheme: 'HTTP'
          }
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3
        }
        {
          type: 'Readiness'
          httpGet: {
            path: '/health/ready'
            port: 8000
            scheme: 'HTTP'
          }
          initialDelaySeconds: 10
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 10
        }
      ]
    }
  ]
  scale: {
    minReplicas: 0
    maxReplicas: 1
    pollingInterval: 30
    cooldownPeriod: 300
    rules: [
      {
        name: 'http'
        http: {
          metadata: {
            concurrentRequests: '10'
          }
        }
      }
    ]
  }
}
```

### Authentication contract

- `platform.enabled` is `true`.
- `globalValidation.requireAuthentication` is `true`.
- `globalValidation.unauthenticatedClientAction` is `RedirectToLoginPage`.
- `globalValidation.redirectToProvider` is `azureactivedirectory`.
- Microsoft Entra provider is enabled with issuer `https://login.microsoftonline.com/${tenant().tenantId}/v2.0` assembled in Bicep.
- The app registration secret is stored only as the Container App secret `entra-client-secret` and referenced by `clientSecretSettingName`.
- Token storage is disabled because the application does not call downstream APIs as the signed-in user.
- The Entra enterprise application has `appRoleAssignmentRequired=true`.
- The `Budget Atlas Demo Users` group is assigned to the enterprise application before the default hostname is shared.
- The redirect URI is `https://ca-sac-budget-atlas-demo.${containerAppsEnvironment.properties.defaultDomain}/.auth/login/aad/callback`.

## Deployment Boundaries

The implementation is deliberately split into three deployments:

1. **Foundation:** resource group, Log Analytics, Container Apps environment, ACR, runtime identity, GitHub identity, federated credential, and RBAC.
2. **Identity and image:** create/configure the Entra app, build and scan the image, push it to ACR, and capture its digest.
3. **Application:** create/update the Container App and its auth configuration using the immutable digest and Entra client secret.

The foundation identity used interactively may create resources and role assignments. The GitHub deployment identity receives only `AcrPush` on the ACR and `Container Apps Contributor` on the resource group after the foundation exists. It does not receive Owner, User Access Administrator, or subscription-wide Contributor.

---

### Task 1: Add the Azure deployment specification and preflight tooling

**Files:**
- Create: `infra/README.md`
- Create: `scripts/Test-AzureDemoPrerequisites.ps1`
- Modify: `docs/azure-deployment-hardening.md`

**Interfaces:**
- Consumes: current Azure CLI login and the repository runtime contract.
- Produces: a read-only preflight command that later tasks use before any deployment.

- [ ] **Step 1: Write the preflight script**

Implement `scripts/Test-AzureDemoPrerequisites.ps1` with `Set-StrictMode -Version Latest` and `$ErrorActionPreference = 'Stop'`. It must:

1. Verify `az version` is at least `2.88.0`.
2. Verify the active subscription name is exactly `Microsoft Azure Enterprise - APPS`.
3. Verify the signed-in tenant display name is `City of Sacramento`.
4. Report, without changing, the registration state of `Microsoft.App`, `Microsoft.OperationalInsights`, `Microsoft.ContainerRegistry`, and `Microsoft.ManagedIdentity`.
5. Verify the operator can run a resource-group deployment validation and can create role assignments, reporting a clear failure before provisioning if not.
6. Verify `az acr check-name --name sacbudgetatlasdemo` returns available.
7. Verify no resource group named `rg-sac-budget-atlas-demo-wus2` already exists, or report its existing resources for review.
8. Print no access tokens, registry credentials, client secrets, subscription IDs, or tenant IDs.

- [ ] **Step 2: Add the Container Apps overlay to the hardening document**

Append a section titled `Experimental Azure Container Apps topology` to `docs/azure-deployment-hardening.md`. Copy the constraints, scale settings, health probes, ephemeral-cache decision, Entra requirement, and expiry date from this plan. Preserve the existing App Service guidance as the later always-on production alternative.

- [ ] **Step 3: Document operator commands**

In `infra/README.md`, document:

```powershell
az login --use-device-code
az account set --subscription 'Microsoft Azure Enterprise - APPS'
pwsh -File scripts/Test-AzureDemoPrerequisites.ps1
```

State that preflight is read-only and that provider registration begins only in Task 3.

- [ ] **Step 4: Verify the script is read-only**

Run:

```powershell
pwsh -NoProfile -File scripts/Test-AzureDemoPrerequisites.ps1
git diff --check
```

Expected: the script reports `Microsoft.App` as `NotRegistered`, makes no Azure changes, and `git diff --check` prints nothing.

- [ ] **Step 5: Commit**

```powershell
git add infra/README.md scripts/Test-AzureDemoPrerequisites.ps1 docs/azure-deployment-hardening.md
git commit -m "docs: specify Azure Container Apps demo preflight"
```

### Task 2: Prove the 0.5-vCPU/1-GiB resource profile

**Files:**
- Create: `docs/azure-container-apps-resource-profile.md`
- Test: `tests/test_live_contract.py`

**Interfaces:**
- Consumes: the production Dockerfile and public ArcGIS source.
- Produces: the final memory value (`1Gi` or `2Gi`) used by `infra/app.bicep`.

- [ ] **Step 1: Build the exact production image**

```powershell
docker build --pull --tag sacramento-budget-atlas:azure-profile .
```

Expected: build succeeds from the pinned Dockerfile.

- [ ] **Step 2: Run a constrained clean-cache refresh**

Create a new Docker volume named `budget-atlas-azure-profile` and run:

```powershell
docker volume create budget-atlas-azure-profile
docker run --rm --name budget-atlas-azure-profile `
  --cpus 0.5 --memory 1g --memory-swap 1g `
  --publish 127.0.0.1:18000:8000 `
  --volume budget-atlas-azure-profile:/var/cache/sacramento-budget `
  --env BUDGET_BACKGROUND_REFRESH_ENABLED=1 `
  --env BUDGET_MANUAL_REFRESH_ENABLED=0 `
  --env APP_ALLOWED_HOSTS=localhost,127.0.0.1 `
  sacramento-budget-atlas:azure-profile
```

In a second shell, poll `http://127.0.0.1:18000/health/ready` and record the time to first `200`. Use `docker stats --no-stream budget-atlas-azure-profile` every five seconds and record peak memory.

- [ ] **Step 3: Apply the sizing gate**

Use `1Gi` only when all conditions pass:

- The container is not OOM-killed.
- Peak memory is below `768 MiB`.
- `/health/ready` returns `200` within five minutes.
- A signed-in-equivalent browser session rendered locally remains responsive for 30 minutes.

If any condition fails, set the planned Container App memory to `2Gi` while keeping CPU at `0.5` and document the observed peak and readiness time.

- [ ] **Step 4: Run the live source contract**

```powershell
uv run --frozen pytest -p no:cacheprovider -m live tests/test_live_contract.py
```

Expected: PASS against the configured public ArcGIS layer.

- [ ] **Step 5: Record and commit the evidence**

Write `docs/azure-container-apps-resource-profile.md` with the image ID, date, resource limits, peak memory, readiness time, and pass/fail decision. Do not commit generated cache data or container logs.

```powershell
git add docs/azure-container-apps-resource-profile.md
git commit -m "docs: record Azure container resource profile"
```

### Task 3: Create subscription- and resource-group-scoped Bicep foundation

**Files:**
- Create: `infra/main.bicep`
- Create: `infra/modules/platform.bicep`
- Create: `infra/parameters/demo.bicepparam`
- Create: `infra/budget.bicep`

**Interfaces:**
- Consumes: exact resource inventory and tags from this plan.
- Produces: `resourceGroupName`, `containerAppsEnvironmentId`, `containerAppsDefaultDomain`, `registryName`, `registryLoginServer`, `runtimeIdentityId`, and `githubIdentityClientId` deployment outputs.

- [ ] **Step 1: Write the subscription-scope entry point**

`infra/main.bicep` must use `targetScope = 'subscription'`, create `rg-sac-budget-atlas-demo-wus2`, and invoke `infra/modules/platform.bicep` at that resource-group scope. Use `westus2` and the exact tags from this plan.

- [ ] **Step 2: Write the platform module**

Use stable API versions:

- `Microsoft.OperationalInsights/workspaces@2025-07-01`
- `Microsoft.App/managedEnvironments@2025-01-01`
- `Microsoft.ContainerRegistry/registries@2025-11-01`
- `Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30`
- `Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30`
- `Microsoft.Authorization/roleAssignments@2022-04-01`

The module must configure:

- Log Analytics `PerGB2018`, 30-day retention, and resource-permission log access.
- A Consumption Container Apps environment linked to the workspace.
- Basic ACR with `adminUserEnabled: false`, `anonymousPullEnabled: false`, and public network access enabled for the experiment.
- Runtime identity with `AcrPull` role ID `7f951dda-4ed3-4680-a7ca-43fe172d538d` scoped to the ACR.
- GitHub identity with `AcrPush` role ID `8311e382-0749-4cb8-b61a-304f252e45ec` scoped to the ACR.
- GitHub identity with `Container Apps Contributor` role ID `358470bc-b998-42bd-ab17-a7e34c199c0f` scoped to the experiment resource group.
- Federated credential issuer `https://token.actions.githubusercontent.com`.
- Federated credential audience `api://AzureADTokenExchange`.
- Federated credential subject `repo:socDocarol/sacramento-budget-atlas:environment:azure-demo`.

- [ ] **Step 3: Write the parameter file**

`infra/parameters/demo.bicepparam` must reference `../main.bicep` and contain only nonsecret experiment values. Use the globally available registry name `sacbudgetatlasdemo`; do not hard-code subscription or tenant IDs.

- [ ] **Step 4: Write the separate advisory budget template**

`infra/budget.bicep` must target subscription scope and define a monthly `$15` `Microsoft.Consumption/budgets` resource with notifications at 50%, 80%, and 100% to `docarol@cityofsacramento.org`. Keep it separate because the current user lacks Cost Management Contributor permission.

- [ ] **Step 5: Compile and lint the templates**

```powershell
az bicep build --file infra/main.bicep
az bicep build --file infra/budget.bicep
az deployment sub validate `
  --location westus2 `
  --template-file infra/main.bicep `
  --parameters infra/parameters/demo.bicepparam
```

Expected: both templates compile; validation either succeeds or identifies the exact missing RBAC/provider prerequisite without creating resources.

- [ ] **Step 6: Review the what-if result**

```powershell
az deployment sub what-if `
  --location westus2 `
  --template-file infra/main.bicep `
  --parameters infra/parameters/demo.bicepparam
```

Expected: only the resource group and foundation resources in the target inventory are created. No VNet, storage account, Key Vault, App Insights, dedicated workload profile, or public application exists.

- [ ] **Step 7: Commit**

```powershell
git add infra/main.bicep infra/modules/platform.bicep infra/parameters/demo.bicepparam infra/budget.bicep
git commit -m "infra: define Container Apps demo foundation"
```

### Task 4: Create the Entra authentication bootstrap

**Files:**
- Create: `scripts/Initialize-AzureDemoIdentity.ps1`
- Create: `docs/azure-container-apps-identity-runbook.md`

**Interfaces:**
- Consumes: `containerAppsDefaultDomain` from the foundation deployment.
- Produces: Entra client ID and a short-lived client secret passed directly to the application deployment; creates no secret file.

- [ ] **Step 1: Write an idempotent identity script**

The script must:

1. Resolve exactly one Entra application named `Sacramento Budget Atlas Demo`; stop if duplicate display names exist.
2. Create it as single tenant when absent.
3. Enable ID-token issuance.
4. Set the sole web redirect URI to the exact Container Apps callback URL.
5. Create the service principal when absent.
6. Set `appRoleAssignmentRequired=true` on the service principal.
7. Resolve exactly one security group named `Budget Atlas Demo Users`; stop with an identity-admin instruction if it does not exist.
8. Assign that group to the enterprise application default access role.
9. Append a client secret named `container-app-auth-2026-08` that expires on `2026-11-30`.
10. Return the client ID and secret in memory to the calling deployment command; never print the secret or write it to disk.

- [ ] **Step 2: Add a safe dry-run mode**

`-WhatIf` must list the app, service principal, redirect URI, group, assignment, and credential changes without executing `az ad app create`, `az ad app update`, `az ad sp create`, `az rest --method PATCH`, `az ad app credential reset`, or group assignment calls.

- [ ] **Step 3: Run the dry run**

```powershell
pwsh -NoProfile -File scripts/Initialize-AzureDemoIdentity.ps1 `
  -ContainerAppsDefaultDomain 'the-domain-output-from-foundation' `
  -WhatIf
```

Expected: the script reports the exact intended callback URL and stops cleanly if the access group is absent.

- [ ] **Step 4: Document identity administration**

The runbook must state the Entra permissions required, the group-owner approval step, the secret expiry date, rotation procedure, and removal procedure. State that all tenant users must not be granted access by default.

- [ ] **Step 5: Commit**

```powershell
git add scripts/Initialize-AzureDemoIdentity.ps1 docs/azure-container-apps-identity-runbook.md
git commit -m "infra: define Entra authentication bootstrap"
```

### Task 5: Define the authenticated Container App

**Files:**
- Create: `infra/app.bicep`
- Create: `infra/parameters/app-demo.bicepparam`

**Interfaces:**
- Consumes: foundation outputs, immutable ACR digest reference, revision suffix, Entra client ID, and in-memory Entra client secret.
- Produces: Container App FQDN, revision name, and authentication resource ID.

- [ ] **Step 1: Write the application Bicep template**

Use:

- `Microsoft.App/containerApps@2025-01-01`
- `Microsoft.App/containerApps/authConfigs@2025-01-01`

Declare the foundation resources as `existing`. Add `@secure()` to `entraClientSecret`. Implement the exact runtime, ingress, scale, probes, environment variables, registry identity, secret reference, and authentication contract from this plan.

- [ ] **Step 2: Prevent unsafe inputs**

Add parameter validation so:

- `imageDigestReference` must contain `@sha256:`.
- `revisionSuffix` must match `sha-` followed by 12 lowercase hexadecimal characters.
- `entraClientId` is nonempty.
- Memory is restricted to `1Gi` or `2Gi`.
- `minReplicas` is fixed at zero and `maxReplicas` is fixed at one rather than exposed as deploy-time parameters.

- [ ] **Step 3: Compile and validate without exposing secrets**

```powershell
az bicep build --file infra/app.bicep
```

Use an in-memory test value for local ARM validation and ensure neither command output nor the generated ARM JSON contains an actual Entra secret.

- [ ] **Step 4: Verify the deployment delta**

Run a resource-group what-if after the foundation and image exist. Expected changes are one Container App and one `authConfigs/current` child resource. The image reference must be a digest, ingress must require HTTPS, and scale must remain 0-1.

- [ ] **Step 5: Commit**

```powershell
git add infra/app.bicep infra/parameters/app-demo.bicepparam
git commit -m "infra: define authenticated Budget Atlas container app"
```

### Task 6: Add the manually approved GitHub deployment workflow

**Files:**
- Create: `.github/workflows/deploy-azure-demo.yml`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: GitHub environment `azure-demo`, foundation outputs, existing CI gates, and `infra/app.bicep`.
- Produces: immutable ACR image and a readiness-gated Container App revision.

- [ ] **Step 1: Preserve CI as the required build gate**

Keep the existing quality, SBOM, and Trivy jobs unchanged except where artifact reuse requires an explicitly versioned upload. Do not grant `id-token: write` to the general CI workflow.

- [ ] **Step 2: Create a manual deployment workflow**

The workflow must:

- Trigger only via `workflow_dispatch` during the first month.
- Define a boolean `deploy` input that defaults to `false`. The first run pushes the image only; later approved runs may set `deploy=true` after the Container App exists.
- Use GitHub environment `azure-demo`.
- Set permissions to `contents: read` and `id-token: write` only.
- Use commit-SHA-pinned third-party actions, following the existing workflow convention.
- Run the same frozen dependency tests and container security scan before Azure login.
- Authenticate with `azure/login` through OIDC using environment secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID`.
- Log in to ACR with the federated GitHub identity.
- Build `budget-atlas:sha-${GITHUB_SHA::12}` once, load that image into Docker, scan that exact local image, and push the same image without rebuilding it.
- Resolve the pushed manifest digest and form `sacbudgetatlasdemo.azurecr.io/budget-atlas@sha256:` followed by the 64-character manifest digest.
- On the first `deploy=false` run, print the immutable digest reference in the workflow summary and stop after the push.
- On later `deploy=true` runs, require the Container App to exist and update only its image digest and revision suffix with `az containerapp update`.
- Never obtain, transmit, or store the Entra client secret in GitHub. The one-time `infra/app.bicep` deployment remains an operator-local action.
- Poll Azure revision state and internal readiness for at most ten minutes.
- Fail without redirecting traffic if readiness never succeeds.

- [ ] **Step 3: Configure the GitHub environment**

Create `azure-demo` with required reviewer `socDocarol`. Store the three Azure identifiers as environment secrets. They are identifiers rather than credentials, but environment scoping ensures the federated subject and reviewer gate match the design.

- [ ] **Step 4: Validate workflow syntax and permissions**

Run the repository's YAML validation tooling if present, then inspect the workflow permissions. Expected: only the deployment job receives `id-token: write`; no publish profile, service-principal password, registry password, or personal access token is present.

- [ ] **Step 5: Commit**

```powershell
git add .github/workflows/deploy-azure-demo.yml .github/workflows/ci.yml
git commit -m "ci: add approved Azure demo deployment"
```

### Task 7: Add demo operations, smoke tests, and rollback

**Files:**
- Create: `scripts/Test-AzureDemoDeployment.ps1`
- Create: `scripts/Warm-AzureDemo.ps1`
- Create: `docs/azure-container-apps-demo-runbook.md`

**Interfaces:**
- Consumes: deployed Container App and authenticated operator CLI session.
- Produces: repeatable pre-demo readiness evidence and rollback instructions.

- [ ] **Step 1: Write the deployment smoke test**

The test script must verify:

1. The public root returns an Entra redirect rather than application content to an unauthenticated request.
2. HTTP redirects to HTTPS or is rejected; insecure content is never served.
3. The active revision image contains `@sha256:`.
4. Scale is exactly min zero and max one.
5. Sticky sessions are enabled and revision mode is Single.
6. The container runs as UID `10001`.
7. `/health/live` and `/health/ready` return `200` from inside the replica.
8. `APP_ALLOWED_HOSTS` exactly contains the Container App FQDN.
9. No `SHINY_TESTMODE` variable exists.
10. A 30-minute authenticated browser session retains working Shiny filters and charts without WebSocket loss.

- [ ] **Step 2: Write the warm-up script**

`scripts/Warm-AzureDemo.ps1` must:

- Resolve the FQDN through `az containerapp show`.
- Send an HTTPS request to trigger scale-up.
- Poll revision replicas every 10 seconds.
- Poll `/health/ready` from inside the replica until it returns `200` or ten minutes elapse.
- Print the FQDN and readiness time.
- Return nonzero when readiness is not reached.

- [ ] **Step 3: Document the demo timeline**

The runbook sequence is:

```text
T-30 minutes: run Warm-AzureDemo.ps1
T-20 minutes: run Test-AzureDemoDeployment.ps1
T-10 minutes: sign in as a member of Budget Atlas Demo Users and exercise filters
T-0: begin demonstration
T+0: take no action; Container Apps scales to zero after traffic and cooldown cease
```

- [ ] **Step 4: Document rollback**

Rollback must redeploy the last known-good immutable digest as a new single revision. Do not use mutable tags and do not switch to multiple revision mode because sticky sessions require single revision mode.

- [ ] **Step 5: Commit**

```powershell
git add scripts/Test-AzureDemoDeployment.ps1 scripts/Warm-AzureDemo.ps1 docs/azure-container-apps-demo-runbook.md
git commit -m "ops: add Azure demo validation and warm-up runbook"
```

### Task 8: Provision only after approval and execute the first deployment

**Files:**
- No new files.

**Interfaces:**
- Consumes: reviewed commits from Tasks 1-7 and approvals from Azure, identity, and GitHub environment owners.
- Produces: the first authenticated experimental deployment.

- [ ] **Step 1: Obtain explicit approvals**

Record approval to:

- Register `Microsoft.App`, `Microsoft.OperationalInsights`, `Microsoft.ContainerRegistry`, and `Microsoft.ManagedIdentity` in APPS when not already registered.
- Create `rg-sac-budget-atlas-demo-wus2` and its listed resources.
- Create or use the `Budget Atlas Demo Users` Entra group.
- Create the Entra application and expiring client secret.
- Add the GitHub OIDC federated credential and GitHub environment.
- Ask a Cost Management Contributor to deploy the `$15` advisory budget.

- [ ] **Step 2: Register providers and wait for completion**

```powershell
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.ManagedIdentity --wait
```

Expected: every provider reports `Registered` in the APPS subscription.

- [ ] **Step 3: Deploy the foundation**

```powershell
az deployment sub create `
  --name budget-atlas-demo-foundation-202608 `
  --location westus2 `
  --template-file infra/main.bicep `
  --parameters infra/parameters/demo.bicepparam
```

Capture outputs in memory for the remaining steps; do not commit generated output files.

- [ ] **Step 4: Initialize Entra authentication**

Run `Initialize-AzureDemoIdentity.ps1` with the environment default-domain output. Confirm the callback URI and access-group assignment before accepting the generated secret.

- [ ] **Step 5: Trigger the approved GitHub deployment**

Run `deploy-azure-demo.yml` for the reviewed commit with `deploy=false`. Approve the `azure-demo` environment gate. Capture the immutable digest reference from the workflow summary.

- [ ] **Step 6: Deploy the authenticated Container App locally**

From the same PowerShell process that holds the newly created Entra secret in memory, deploy `infra/app.bicep` with the immutable image digest, a revision suffix formed as `sha-` plus the first 12 lowercase hexadecimal characters of the Git commit, the Entra client ID, and the secure Entra client-secret parameter. Confirm the secret is not printed, written to a parameter file, stored in shell history, or sent to GitHub.

- [ ] **Step 7: Run all smoke tests**

Run `Warm-AzureDemo.ps1` and `Test-AzureDemoDeployment.ps1`. Expected: authenticated application is ready, unauthenticated access redirects to Entra, the active image is immutable, and scale is 0-1.

- [ ] **Step 8: Verify scale-to-zero and costs**

After testing stops, confirm the running replica count reaches zero. Within 24 hours, review Container Apps, ACR, and Log Analytics cost meters. Escalate if forecasted monthly incremental cost exceeds `$15`.

- [ ] **Step 9: Schedule the expiry review**

Create an operational review for `2026-09-30` to choose one of:

- Remove the experimental resource group and Entra application.
- Extend the experiment with a new expiry tag and rotated auth secret.
- Design an always-on or persistent-cache release based on observed memory, startup, and usage telemetry.

---

## Verification Matrix

| Requirement | Evidence |
|---|---|
| No public anonymous access | Unauthenticated root receives Entra redirect; assigned team user succeeds |
| Scale-to-zero | Replica count reaches zero after inactivity |
| Stateful session safety | Maximum replicas is one; sticky sessions enabled; 30-minute WebSocket test passes |
| Safe cold start | `/health/live` succeeds before `/health/ready`; warm-up completes within ten minutes |
| Immutable release | Active image reference contains the pushed SHA-256 digest |
| No long-lived GitHub Azure secret | Workflow uses OIDC and contains no service-principal password |
| No registry password | ACR admin and anonymous pull are disabled; managed identity has AcrPull |
| Least-privilege deployment | GitHub identity has AcrPush on ACR and Container Apps Contributor on experiment RG only |
| Cost containment | Consumption environment, 0-1 replicas, Basic ACR, 30-day logs, no optional infrastructure |
| Recovery | Known-good digest can be redeployed as a new single revision |
| Time-bounded experiment | `expiresOn=2026-09-30` and an expiry review is scheduled |

## Deferred Work

The following is explicitly outside this experiment and requires a separate design:

- Public City launch and communications approval.
- Custom City domain and DNS.
- Persistent Azure Files or Blob snapshot storage.
- Scheduled ingestion jobs and distributed refresh coordination.
- Multiple web replicas or regional redundancy.
- Private networking, private endpoints, WAF, Front Door, or Application Gateway.
- Formal production SLO, on-call rotation, disaster recovery, and load testing.
- City billing-account/MACC confirmation, which requires a Cost Management role the current account does not have.

## Primary Azure References

- [Azure Container Apps pricing and monthly free grant](https://azure.microsoft.com/en-us/pricing/details/container-apps/)
- [Azure Container Apps scaling](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [Azure Container Apps session affinity](https://learn.microsoft.com/en-us/azure/container-apps/sticky-sessions)
- [Azure Container Apps health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [Azure Container Apps revisions](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
- [Azure Container Apps Microsoft Entra authentication](https://learn.microsoft.com/en-us/azure/container-apps/authentication)
- [Managed-identity image pulls from ACR](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull)
- [GitHub Actions authentication to Azure with OIDC](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)
- [Azure container RBAC roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/containers)
- [Create Azure budgets with Bicep](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/quick-create-budget-bicep)
