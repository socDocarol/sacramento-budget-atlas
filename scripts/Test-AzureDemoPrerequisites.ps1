[CmdletBinding()]
param(
    [string]$AzCommand = 'az'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$expectedSubscription = 'Microsoft Azure Enterprise - APPS'
$expectedTenant = 'City of Sacramento'
$resourceGroupName = 'rg-sac-budget-atlas-demo-wus2'
$registryName = 'sacbudgetatlasdemo'
$providerNamespaces = @(
    'Microsoft.App',
    'Microsoft.OperationalInsights',
    'Microsoft.ContainerRegistry',
    'Microsoft.ManagedIdentity'
)

function Invoke-AzJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $raw = & $AzCommand @Arguments --output json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
    if ([string]::IsNullOrWhiteSpace(($raw -join "`n"))) {
        return $null
    }
    return ($raw -join "`n") | ConvertFrom-Json
}

function Test-ActionAllowed {
    param(
        [Parameter(Mandatory = $true)]$Permissions,
        [Parameter(Mandatory = $true)][string]$Action
    )

    foreach ($permission in $Permissions) {
        $allowed = $false
        foreach ($candidate in $permission.actions) {
            if ($candidate -eq '*' -or $candidate -eq $Action) {
                $allowed = $true
                break
            }
            if ($candidate.EndsWith('/*')) {
                $prefix = $candidate.Substring(0, $candidate.Length - 1)
                if ($Action.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    $allowed = $true
                    break
                }
            }
        }
        if (-not $allowed) {
            continue
        }

        $denied = $false
        foreach ($candidate in $permission.notActions) {
            if ($candidate -eq '*' -or $candidate -eq $Action) {
                $denied = $true
                break
            }
            if ($candidate.EndsWith('/*')) {
                $prefix = $candidate.Substring(0, $candidate.Length - 1)
                if ($Action.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    $denied = $true
                    break
                }
            }
        }
        if (-not $denied) {
            return $true
        }
    }
    return $false
}

$versionData = Invoke-AzJson -Arguments @('version')
$cliVersion = [version]$versionData.'azure-cli'
if ($cliVersion -lt [version]'2.88.0') {
    throw "Azure CLI 2.88.0 or newer is required; found $cliVersion."
}

$account = Invoke-AzJson -Arguments @('account', 'show')
if ($account.name -ne $expectedSubscription) {
    throw "Select the '$expectedSubscription' subscription before continuing."
}
if ($account.tenantDisplayName -ne $expectedTenant) {
    throw "Sign in to the '$expectedTenant' tenant before continuing."
}

Write-Output "Azure CLI: $cliVersion"
Write-Output "Subscription: $expectedSubscription"
Write-Output "Tenant: $expectedTenant"
Write-Output 'Resource-provider registration states:'
foreach ($namespace in $providerNamespaces) {
    $provider = Invoke-AzJson -Arguments @('provider', 'show', '--namespace', $namespace)
    Write-Output "  $namespace`: $($provider.registrationState)"
}

$permissionsUrl = "https://management.azure.com/subscriptions/$($account.id)/providers/Microsoft.Authorization/permissions?api-version=2022-04-01"
$permissionResult = Invoke-AzJson -Arguments @('rest', '--method', 'get', '--url', $permissionsUrl)
$requiredActions = @(
    'Microsoft.Resources/deployments/validate/action',
    'Microsoft.Resources/deployments/write',
    'Microsoft.Authorization/roleAssignments/write'
)
foreach ($action in $requiredActions) {
    if (-not (Test-ActionAllowed -Permissions $permissionResult.value -Action $action)) {
        throw "The signed-in account lacks required permission '$action'. Request the necessary Azure role before provisioning."
    }
}
Write-Output 'Deployment and role-assignment permissions: available'

$nameCheck = Invoke-AzJson -Arguments @('acr', 'check-name', '--name', $registryName)
if (-not $nameCheck.nameAvailable) {
    throw "Azure Container Registry name '$registryName' is no longer available. Review the infrastructure name before provisioning."
}
Write-Output "Container Registry name available: $registryName"

$groupExistsRaw = & $AzCommand group exists --name $resourceGroupName --output tsv
if ($LASTEXITCODE -ne 0) {
    throw "Azure CLI command failed: az group exists --name $resourceGroupName"
}
$groupExists = [System.Convert]::ToBoolean(($groupExistsRaw -join '').Trim())
if ($groupExists) {
    Write-Output "Resource group already exists: $resourceGroupName"
    $resources = Invoke-AzJson -Arguments @('resource', 'list', '--resource-group', $resourceGroupName)
    foreach ($resource in $resources) {
        Write-Output "  $($resource.type): $($resource.name)"
    }
} else {
    Write-Output "Resource group is available for creation: $resourceGroupName"
}

Write-Output 'Azure demo preflight passed.'
Write-Output 'No Azure resources were changed.'
