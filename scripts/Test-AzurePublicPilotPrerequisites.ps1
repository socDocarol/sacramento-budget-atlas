[CmdletBinding()]
param(
    [string]$AzCommand = 'az'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$expectedSubscription = 'Microsoft Azure Enterprise - DBA'
$expectedTenant = 'City of Sacramento'
$dbaResourceGroupName = 'DBA'
$environmentName = 'saccity-shared-env'
$registryResourceGroupName = 'Databricks'
$registryName = 'saccitydaoregistry'
$containerAppName = 'ca-sac-budget-atlas-public-pilot'
$providerNamespaces = @('Microsoft.App', 'Microsoft.ContainerRegistry', 'Microsoft.ManagedIdentity')

function Invoke-AzJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $raw = & $AzCommand @Arguments --output json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
    $text = $raw -join "`n"
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }
    return $text | ConvertFrom-Json
}

function Test-ActionAllowed {
    param(
        [Parameter(Mandatory = $true)]$Permissions,
        [Parameter(Mandatory = $true)][string]$Action
    )

    foreach ($permission in $Permissions) {
        $allowed = $false
        foreach ($candidate in @($permission.actions)) {
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
        foreach ($candidate in @($permission.notActions)) {
            if ($candidate -eq '*' -or $candidate -eq $Action) {
                $allowed = $false
                break
            }
            if ($candidate.EndsWith('/*')) {
                $prefix = $candidate.Substring(0, $candidate.Length - 1)
                if ($Action.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    $allowed = $false
                    break
                }
            }
        }
        if ($allowed) {
            return $true
        }
    }
    return $false
}

function Assert-Permissions {
    param(
        [Parameter(Mandatory = $true)][string]$Scope,
        [Parameter(Mandatory = $true)][string[]]$Actions
    )

    $permissionsUrl = "https://management.azure.com$Scope/providers/Microsoft.Authorization/permissions?api-version=2022-04-01"
    $permissionResult = Invoke-AzJson -Arguments @('rest', '--method', 'get', '--url', $permissionsUrl)
    foreach ($action in $Actions) {
        if (-not (Test-ActionAllowed -Permissions $permissionResult.value -Action $action)) {
            throw "The signed-in account lacks required permission '$action' at scope '$Scope'. Request only a role that grants this operation at this scope."
        }
    }
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

$dbaScope = "/subscriptions/$($account.id)/resourceGroups/$dbaResourceGroupName"
$registryScope = "/subscriptions/$($account.id)/resourceGroups/$registryResourceGroupName/providers/Microsoft.ContainerRegistry/registries/$registryName"
Assert-Permissions -Scope $dbaScope -Actions @(
    'Microsoft.Resources/deployments/validate/action',
    'Microsoft.Resources/deployments/write',
    'Microsoft.ManagedIdentity/userAssignedIdentities/write',
    'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/write',
    'Microsoft.App/containerApps/write',
    'Microsoft.Authorization/roleAssignments/write'
)
Assert-Permissions -Scope $registryScope -Actions @('Microsoft.Authorization/roleAssignments/write')
Write-Output 'Deployment and scoped role-assignment permissions: available'

$environment = Invoke-AzJson -Arguments @(
    'containerapp', 'env', 'show', '--resource-group', $dbaResourceGroupName, '--name', $environmentName
)
if ($environment.name -cne $environmentName -or $environment.resourceGroup -cne $dbaResourceGroupName) {
    throw "The shared Container Apps environment '$environmentName' was not found in resource group '$dbaResourceGroupName'."
}
$consumptionProfiles = @($environment.properties.workloadProfiles | Where-Object {
        $_.name -ceq 'Consumption' -and $_.workloadProfileType -ceq 'Consumption'
    })
if ($consumptionProfiles.Count -ne 1) {
    throw "The shared environment must expose exactly one Consumption workload profile before deployment."
}
if ($environment.properties.appLogsConfiguration.destination -cne 'log-analytics') {
    throw "The shared environment logging destination must remain 'log-analytics'."
}
Write-Output 'Shared environment: saccity-shared-env in DBA'
Write-Output 'Consumption workload profile: available'
Write-Output 'Shared logging destination: log-analytics'

$registry = Invoke-AzJson -Arguments @(
    'acr', 'show', '--resource-group', $registryResourceGroupName, '--name', $registryName
)
if ($registry.name -cne $registryName -or $registry.resourceGroup -cne $registryResourceGroupName) {
    throw "The shared registry '$registryName' was not found in resource group '$registryResourceGroupName'."
}
if ($registry.sku.name -cne 'Basic' -or $registry.loginServer -cne 'saccitydaoregistry.azurecr.io') {
    throw "The shared registry does not match the approved Basic registry contract."
}
if ($registry.anonymousPullEnabled -eq $true) {
    throw 'The shared registry must not allow anonymous image pulls.'
}
Write-Output 'Shared registry: saccitydaoregistry in Databricks (Basic, private pull)'

$apps = @(Invoke-AzJson -Arguments @('containerapp', 'list', '--resource-group', $dbaResourceGroupName))
$targetMatches = @($apps | Where-Object { $_.name -ceq $containerAppName })
if ($targetMatches.Count -gt 1) {
    throw "Multiple Container Apps named '$containerAppName' were returned. Stop and resolve the inventory ambiguity."
}
if ($targetMatches.Count -eq 1) {
    Write-Output "Pilot Container App already exists and will require preview review: $containerAppName"
} else {
    Write-Output "Pilot Container App name is available in DBA: $containerAppName"
}
$siblingNames = @($apps | Where-Object { $_.name -cne $containerAppName } | ForEach-Object { $_.name })
Write-Output "Existing sibling Container Apps observed: $($siblingNames -join ', ')"

Write-Output 'Azure public pilot preflight passed.'
Write-Output 'No Azure resources were changed.'
