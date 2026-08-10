# Azure public-pilot infrastructure

This directory defines the time-limited, anonymously accessible Budget Atlas
Container App in the `Microsoft Azure Enterprise - DBA` subscription. It
reuses existing DBA platform resources and must not change their configuration.

## Shared dependencies

- Container Apps environment `saccity-shared-env` in resource group `DBA`.
- Workload profile `Consumption` in that environment.
- Container registry `saccitydaoregistry` in resource group `Databricks`.
- Logging already configured on the shared environment.

The templates do not create a resource group, Container Apps environment,
registry, Log Analytics workspace, budget, or employee sign-in application.
They create only two pilot identities, their federated and registry role
assignments, one Budget Atlas Container App, and an app-scoped deployment role
assignment.

## Deployment boundaries

`main.bicep` runs at subscription scope only because it coordinates modules in
the two existing resource groups. The identities module creates separate
runtime and GitHub OIDC identities in `DBA`; the registry-access module grants
only `AcrPull` to the runtime identity and `AcrPush` to the GitHub identity on
the shared registry.

`app.bicep` runs in `DBA`. It creates the Budget Atlas app on Consumption and
grants the GitHub identity Container Apps Contributor only on that app
resource. It declares the environment, registry, and identities as existing.

Visitor access is anonymous HTTPS. The app serves `robots.txt` and returns
`X-Robots-Tag: noindex, nofollow`. Search exclusion is not access control; the
URL remains public to anyone who obtains or discovers it.

## Read-only preflight

```powershell
az login --use-device-code
az account set --subscription 'Microsoft Azure Enterprise - DBA'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Test-AzurePublicPilotPrerequisites.ps1
```

The preflight checks CLI/account context, exact shared resources, Consumption,
logging, sibling Container Apps, and effective permissions. It does not
register providers, create resources, assign roles, or deploy anything.

## Validation and operations

The complete preview, bootstrap, first-image deployment, smoke test, rollback,
scale-to-zero, and expiry procedures are in
[`docs/azure-container-apps-public-pilot-runbook.md`](../docs/azure-container-apps-public-pilot-runbook.md).
Do not add the resolved pilot hostname or URL to repository documentation.
