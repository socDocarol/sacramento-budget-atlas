# Azure demo infrastructure

This directory will define the disposable Azure Container Apps deployment for
internal team testing and scheduled demonstrations. The deployment targets the
`Microsoft Azure Enterprise - APPS` subscription in `westus2`.

The first-month topology is intentionally small:

- Azure Container Apps Consumption with zero to one replicas.
- One `0.5` vCPU container with `1Gi` memory, subject to the resource-profile
  gate in the implementation plan.
- Basic Azure Container Registry with managed-identity pulls.
- Log Analytics with 30-day retention.
- Microsoft Entra authentication restricted to an assigned team group.
- Ephemeral prepared-data cache and an explicit pre-demo warm-up.

The complete design, ordered implementation steps, and verification matrix are
in
[`docs/superpowers/plans/2026-08-09-azure-container-apps-demo.md`](../docs/superpowers/plans/2026-08-09-azure-container-apps-demo.md).

## Read-only preflight

Sign in and select the intended subscription:

```powershell
az login --use-device-code
az account set --subscription 'Microsoft Azure Enterprise - APPS'
pwsh -NoProfile -File scripts/Test-AzureDemoPrerequisites.ps1
```

On Windows systems without PowerShell 7, use Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Test-AzureDemoPrerequisites.ps1
```

The preflight reads CLI version, account context, provider-registration state,
effective deployment permissions, global ACR-name availability, and the target
resource-group state. It does not register providers, create a resource group,
assign roles, or deploy resources.

As of 2026-08-09, the signed-in account can inspect the APPS subscription but
does not have the deployment-validation and role-assignment permissions needed
to provision this design. `Microsoft.App` is also not registered. Those are
approval prerequisites, not actions performed by preflight.

