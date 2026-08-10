param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9.-]+\.azurecontainerapps\.io$')]
    [string]$ContainerAppsDefaultDomain,

    [string]$AzCommand = 'az',

    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

$appDisplayName = 'Sacramento Budget Atlas Demo'
$groupDisplayName = 'Budget Atlas Demo Users'
$containerAppName = 'ca-sac-budget-atlas-demo'
$credentialDisplayName = 'container-app-auth-2026-08'
$credentialEndDate = '2026-11-30T23:59:59Z'
$defaultAccessRoleId = '00000000-0000-0000-0000-000000000000'
$callbackUrl = "https://$containerAppName.$ContainerAppsDefaultDomain/.auth/login/aad/callback"

function Invoke-AzJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $raw = & $AzCommand @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: $($Arguments[0..1] -join ' '). Review Azure CLI authentication and permissions."
    }
    $text = $raw -join "`n"
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }
    return $text | ConvertFrom-Json
}

function ConvertTo-ObjectArray {
    param($Value)

    if ($null -eq $Value) {
        return @()
    }
    return @($Value)
}

function Get-ExactDisplayNameMatch {
    param(
        [Parameter(Mandatory = $true)][AllowNull()]$Candidates,
        [Parameter(Mandatory = $true)][string]$DisplayName,
        [Parameter(Mandatory = $true)][string]$ObjectKind
    )

    $matches = @(ConvertTo-ObjectArray $Candidates | Where-Object { $_.displayName -ceq $DisplayName })
    if ($matches.Count -gt 1) {
        throw "Multiple $ObjectKind objects named '$DisplayName' exist. Resolve the duplicate display names before continuing."
    }
    return $matches
}

Write-Output "Container Apps authentication callback: $callbackUrl"

$apps = Invoke-AzJson @('ad', 'app', 'list', '--display-name', $appDisplayName, '--output', 'json')
$appMatches = @(Get-ExactDisplayNameMatch -Candidates $apps -DisplayName $appDisplayName -ObjectKind 'Entra application')

$groups = Invoke-AzJson @('ad', 'group', 'list', '--display-name', $groupDisplayName, '--output', 'json')
$groupMatches = @(Get-ExactDisplayNameMatch -Candidates $groups -DisplayName $groupDisplayName -ObjectKind 'Entra group')
if ($groupMatches.Count -eq 0) {
    throw "The '$groupDisplayName' security group does not exist. Ask an identity administrator or approved group owner to create it before continuing."
}
$group = $groupMatches[0]
if ($group.securityEnabled -ne $true) {
    throw "The '$groupDisplayName' object is not security-enabled. Ask an identity administrator to provide a security group."
}

$app = if ($appMatches.Count -eq 1) { $appMatches[0] } else { $null }
$servicePrincipal = $null
$existingAssignment = $null
$matchingCredentials = @()

if ($null -ne $app) {
    $matchingCredentials = @(ConvertTo-ObjectArray $app.passwordCredentials | Where-Object {
            $_.displayName -ceq $credentialDisplayName
        })
    $servicePrincipals = Invoke-AzJson @(
        'ad', 'sp', 'list', '--filter', "appId eq '$($app.appId)'", '--output', 'json'
    )
    $servicePrincipalMatches = @(ConvertTo-ObjectArray $servicePrincipals | Where-Object {
            $_.appId -ceq $app.appId
        })
    if ($servicePrincipalMatches.Count -gt 1) {
        throw "Multiple service principals reference application '$appDisplayName'. Resolve the duplicate objects before continuing."
    }
    if ($servicePrincipalMatches.Count -eq 1) {
        $servicePrincipal = $servicePrincipalMatches[0]
        $assignmentUri = "https://graph.microsoft.com/v1.0/groups/$($group.id)/appRoleAssignments?`$filter=resourceId%20eq%20$($servicePrincipal.id)"
        $assignmentResponse = Invoke-AzJson @('rest', '--method', 'GET', '--uri', $assignmentUri, '--output', 'json')
        $existingAssignment = @(ConvertTo-ObjectArray $assignmentResponse.value | Where-Object {
                $_.resourceId -ceq $servicePrincipal.id -and $_.appRoleId -ceq $defaultAccessRoleId
            }) | Select-Object -First 1
    }
}

if ($WhatIf) {
    if ($null -eq $app) {
        Write-Output "Would create the single-tenant Entra application '$appDisplayName' with ID tokens enabled."
        Write-Output 'Would create its enterprise application service principal.'
    }
    else {
        Write-Output "Would update '$appDisplayName' to single-tenant, enable ID tokens, and set the sole redirect URI."
        if ($null -eq $servicePrincipal) {
            Write-Output 'Would create its enterprise application service principal.'
        }
    }
    Write-Output "Would require explicit assignment on the enterprise application."
    Write-Output "Resolved security group '$groupDisplayName'; would assign its default access role if absent."
    if ($matchingCredentials.Count -eq 0) {
        Write-Output "Would append '$credentialDisplayName' expiring $credentialEndDate."
    }
    else {
        Write-Output "Credential '$credentialDisplayName' already exists; an actual run would stop rather than create a duplicate."
    }
    Write-Output 'WhatIf completed. No Entra objects, assignments, or credentials were changed.'
    return
}

if ($matchingCredentials.Count -gt 0) {
    throw "Credential '$credentialDisplayName' already exists and its value cannot be retrieved. Remove or rotate it through the approved procedure instead of creating a duplicate."
}

if ($null -eq $app) {
    $app = Invoke-AzJson @(
        'ad', 'app', 'create',
        '--display-name', $appDisplayName,
        '--sign-in-audience', 'AzureADMyOrg',
        '--enable-id-token-issuance', 'true',
        '--web-redirect-uris', $callbackUrl,
        '--output', 'json'
    )
}
else {
    Invoke-AzJson @(
        'ad', 'app', 'update',
        '--id', $app.appId,
        '--sign-in-audience', 'AzureADMyOrg',
        '--enable-id-token-issuance', 'true',
        '--web-redirect-uris', $callbackUrl,
        '--output', 'json'
    ) | Out-Null
}

if ($null -eq $servicePrincipal) {
    $servicePrincipal = Invoke-AzJson @('ad', 'sp', 'create', '--id', $app.appId, '--output', 'json')
}

$servicePrincipalPatch = @{ appRoleAssignmentRequired = $true } | ConvertTo-Json -Compress
Invoke-AzJson @(
    'rest', '--method', 'PATCH',
    '--uri', "https://graph.microsoft.com/v1.0/servicePrincipals/$($servicePrincipal.id)",
    '--headers', 'Content-Type=application/json',
    '--body', $servicePrincipalPatch,
    '--output', 'json'
) | Out-Null

if ($null -eq $existingAssignment) {
    $assignmentBody = @{
        principalId = $group.id
        resourceId = $servicePrincipal.id
        appRoleId = $defaultAccessRoleId
    } | ConvertTo-Json -Compress
    Invoke-AzJson @(
        'rest', '--method', 'POST',
        '--uri', "https://graph.microsoft.com/v1.0/groups/$($group.id)/appRoleAssignments",
        '--headers', 'Content-Type=application/json',
        '--body', $assignmentBody,
        '--output', 'json'
    ) | Out-Null
}

$credentialRaw = & $AzCommand ad app credential reset `
    --id $app.appId `
    --append `
    --display-name $credentialDisplayName `
    --end-date $credentialEndDate `
    --output json 2>&1
if ($LASTEXITCODE -ne 0) {
    throw 'Azure CLI could not append the Container Apps authentication credential. No secret value was retained.'
}
$credential = ($credentialRaw -join "`n") | ConvertFrom-Json
$secureSecret = ConvertTo-SecureString -String $credential.password -AsPlainText -Force
$credential = $null
$credentialRaw = $null

[pscustomobject]@{
    ClientId = [string]$app.appId
    ClientSecret = $secureSecret
    SecretExpiresOn = [datetimeoffset]$credentialEndDate
}
