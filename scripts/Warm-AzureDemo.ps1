param(
    [string]$ResourceGroupName = 'rg-sac-budget-atlas-demo-wus2',
    [string]$ContainerAppName = 'ca-sac-budget-atlas-demo',
    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 600,
    [string]$AzCommand = 'az',
    [string]$WebProbeCommand
)

$ErrorActionPreference = 'Stop'

function Invoke-AzJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $raw = & $AzCommand @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: $($Arguments[0..1] -join ' ')."
    }
    return ($raw -join "`n") | ConvertFrom-Json
}

function Invoke-WebProbe {
    param([Parameter(Mandatory = $true)][string]$Uri)

    if (-not [string]::IsNullOrWhiteSpace($WebProbeCommand)) {
        $raw = & $WebProbeCommand -Uri $Uri 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Web probe command failed for $Uri."
        }
        return ($raw -join "`n") | ConvertFrom-Json
    }

    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    try {
        $response = $client.GetAsync($Uri).GetAwaiter().GetResult()
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode }
    }
    catch {
        return [pscustomobject]@{ StatusCode = 0 }
    }
    finally {
        $client.Dispose()
        $handler.Dispose()
    }
}

$startedAt = Get-Date
$deadline = $startedAt.AddSeconds($TimeoutSeconds)
$app = Invoke-AzJson @(
    'containerapp', 'show', '--name', $ContainerAppName, '--resource-group', $ResourceGroupName, '--output', 'json'
)
$fqdn = [string]$app.properties.configuration.ingress.fqdn
$revisionName = [string]$app.properties.latestRevisionName
if ([string]::IsNullOrWhiteSpace($fqdn) -or [string]::IsNullOrWhiteSpace($revisionName)) {
    throw 'The Container App FQDN or latest revision could not be resolved.'
}

$trigger = Invoke-WebProbe -Uri "https://$fqdn/"
if ([int]$trigger.StatusCode -eq 0) {
    throw "The HTTPS warm-up request to $fqdn failed before reaching Container Apps."
}

while ((Get-Date) -lt $deadline) {
    $replicas = Invoke-AzJson @(
        'containerapp', 'replica', 'list', '--name', $ContainerAppName,
        '--resource-group', $ResourceGroupName, '--revision', $revisionName, '--output', 'json'
    )
    $replica = @($replicas)[0]
    if ($null -ne $replica) {
        $readyRaw = & $AzCommand containerapp exec `
            --name $ContainerAppName `
            --resource-group $ResourceGroupName `
            --revision $revisionName `
            --replica $replica.name `
            --command "python -c `"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5).status)`"" 2>&1
        if ($LASTEXITCODE -eq 0 -and ($readyRaw -join "`n") -match '(?m)^\s*200\s*$') {
            $elapsed = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)
            Write-Output "Azure demo is ready at https://$fqdn/ after $elapsed seconds."
            return
        }
    }
    Start-Sleep -Seconds 10
}

throw "Azure demo at https://$fqdn/ did not reach internal readiness within $TimeoutSeconds seconds."
