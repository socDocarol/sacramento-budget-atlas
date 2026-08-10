# Azure Container Apps public-pilot runbook

This runbook operates the anonymous Budget Atlas pilot in the existing DBA
Container Apps platform. It does not authorize changes to shared platform
configuration or existing Container Apps. Never paste the resolved pilot URL
into repository files, issues, workflow summaries, or pull-request text.

## Fixed inventory

| Boundary | Value |
| --- | --- |
| Subscription | `Microsoft Azure Enterprise - DBA` |
| Region | `westus2` |
| App resource group | `DBA` |
| Existing environment | `saccity-shared-env` |
| Existing workload profile | `Consumption` |
| Registry resource group | `Databricks` |
| Existing registry | `saccitydaoregistry` |
| New Container App | `ca-sac-budget-atlas-public-pilot` |
| GitHub environment | `azure-public-pilot` |
| Review or removal date | `2026-09-30` |

The visitor boundary is anonymous HTTPS. GitHub authenticates to Azure with
OIDC. The running app pulls its private image through a separate runtime
managed identity. Search exclusion is not access control; `robots.txt` and
`X-Robots-Tag` do not prevent a person from reaching a discovered URL.

## 1. Select context and run read-only preflight

```powershell
az login --use-device-code
az account set --subscription 'Microsoft Azure Enterprise - DBA'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Test-AzurePublicPilotPrerequisites.ps1
```

Stop if preflight reports the wrong subscription, a missing Consumption
profile, a mismatched shared resource, or a missing permission. Do not register
providers or alter shared resources to make preflight pass.

## 2. Build and validate Bicep locally

```powershell
az bicep build --file infra/main.bicep --stdout | Out-Null
az bicep build --file infra/app.bicep --stdout | Out-Null
az deployment sub validate `
  --name budget-atlas-public-pilot-bootstrap-validation `
  --location westus2 `
  --template-file infra/main.bicep `
  --parameters infra/parameters/public-pilot.bicepparam
az deployment sub what-if `
  --name budget-atlas-public-pilot-bootstrap-preview `
  --location westus2 `
  --template-file infra/main.bicep `
  --parameters infra/parameters/public-pilot.bicepparam
```

The subscription preview may contain nested deployments into `DBA` and
`Databricks`. The effective changes must be limited to:

- Two Budget Atlas user-assigned identities in `DBA`.
- One GitHub federated identity credential.
- Runtime `AcrPull` and GitHub `AcrPush` assignments on the shared registry.

Reject a preview that creates or modifies a resource group, environment,
registry, logging workspace, existing Container App, or shared resource tags.

## 3. Bootstrap pilot identities

After the preview passes:

```powershell
az deployment sub create `
  --name budget-atlas-public-pilot-bootstrap `
  --location westus2 `
  --template-file infra/main.bicep `
  --parameters infra/parameters/public-pilot.bicepparam
```

Configure the protected GitHub environment `azure-public-pilot` with a required
reviewer. Set its `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and
`AZURE_SUBSCRIPTION_ID` values from the approved Azure context and bootstrap
output. These are identifiers, not passwords. Do not create an Azure client
secret, publish profile, registry password, or personal access token.

## 4. Build, scan, and push the first immutable image

Run `.github/workflows/deploy-azure-public-pilot.yml` with `deploy=false` for
the reviewed commit. The job must pass frozen dependency sync, Ruff, unit
tests, one Docker build, SPDX SBOM generation, and Trivy high/critical scanning
before OIDC login and registry push. Copy the immutable digest reference and
revision suffix from the protected workflow result into the current shell.

```powershell
$env:BUDGET_ATLAS_IMAGE_DIGEST = '<registry/repository@sha256:digest>'
$env:BUDGET_ATLAS_REVISION_SUFFIX = 'sha-<12 lowercase commit characters>'
```

Do not save either value to a tracked parameter file. The digest is not a
secret, but keeping release inputs ephemeral prevents stale deployments.

## 5. Preview and create the Budget Atlas app

```powershell
az deployment group validate `
  --name budget-atlas-public-pilot-app-validation `
  --resource-group DBA `
  --template-file infra/app.bicep `
  --parameters infra/parameters/app-public-pilot.bicepparam
az deployment group what-if `
  --name budget-atlas-public-pilot-app-preview `
  --resource-group DBA `
  --template-file infra/app.bicep `
  --parameters infra/parameters/app-public-pilot.bicepparam
```

The app preview must create only the new Budget Atlas Container App and the
GitHub Container Apps Contributor assignment scoped to that app. It must not
show changes to `saccity-shared-env`, `saccitydaoregistry`, shared logging,
`saccityapps`, `next311`, or any other sibling resource.

After reviewing the preview:

```powershell
az deployment group create `
  --name budget-atlas-public-pilot-app `
  --resource-group DBA `
  --template-file infra/app.bicep `
  --parameters infra/parameters/app-public-pilot.bicepparam
Remove-Item Env:BUDGET_ATLAS_IMAGE_DIGEST
Remove-Item Env:BUDGET_ATLAS_REVISION_SUFFIX
```

## 6. Validate the deployed pilot

Warm the scale-to-zero app without recording its URL:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Warm-AzurePublicPilot.ps1
```

In a browser, anonymously exercise a real Shiny session for at least 30
minutes. Confirm filters, charts, navigation, and the WebSocket remain working.
Record the active revision name, duration, and pass decision outside the public
repository, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Test-AzurePublicPilotDeployment.ps1 `
  -BrowserSessionRevisionName '<active revision>' `
  -BrowserSessionDurationMinutes 30 `
  -BrowserSessionPassed
```

The smoke test verifies anonymous HTTPS, indexing-exclusion responses,
Consumption, immutable digest, runtime identity pull, single revision, sticky
sessions, scale zero-to-one, exact allowed host, disabled manual refresh,
non-root UID, and both internal health probes.

## 7. Routine deployment

Run the protected workflow with `deploy=true`. It rebuilds and rechecks the
selected commit, pushes the scanned image, resolves the digest, confirms the
pilot app exists, updates only its image and revision suffix, and waits for the
new revision to become healthy. The prior single revision retains traffic if
the new revision fails before activation.

## 8. Rollback

Redeploy a known-good immutable digest as a new single revision. Never use a
mutable tag or switch to multiple revision mode.

```powershell
az containerapp update `
  --name ca-sac-budget-atlas-public-pilot `
  --resource-group DBA `
  --image '<known-good registry/repository@sha256:digest>' `
  --revision-suffix 'sha-<known-good 12 lowercase commit characters>' `
  --output none
```

Warm and rerun the deployment smoke test against the rollback revision.

## 9. Scale-to-zero, cost, and expiry review

After test traffic stops and the cooldown elapses, confirm the replica count
returns to zero. Review Container Apps consumption, shared registry storage,
log ingestion, and network egress for unexpected marginal cost. The monthly
free grants are subscription-wide and are not a guarantee of zero cost.

By `2026-09-30`, choose one action:

1. Remove only the Budget Atlas Container App, the two Budget Atlas identities,
   the federated credential, and their role assignments.
2. Extend the pilot with a new review tag and documented approval.
3. Return to the hardened design for a longer-lived application.

Never delete either shared resource group or any shared environment, registry,
logging, or sibling Container App as part of pilot cleanup.

## Narrow RBAC escalation

If Azure denies an operation, capture the exact operation and resource scope.
For example, report `Microsoft.Authorization/roleAssignments/write` at the
specific app or registry scope when that is the denied operation. Request only
the role that grants that operation at that scope; do not ask for subscription
Owner or for the DBA owner to package or deploy the application.
