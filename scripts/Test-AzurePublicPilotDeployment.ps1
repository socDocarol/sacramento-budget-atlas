param(
    [string]$ResourceGroupName = 'DBA',
    [string]$ContainerAppName = 'ca-sac-budget-atlas-public-pilot',
    [string]$BrowserSessionRevisionName,
    [int]$BrowserSessionDurationMinutes = 0,
    [switch]$BrowserSessionPassed,
    [string]$AzCommand = 'az',
    [string]$WebProbeCommand
)

$ErrorActionPreference = 'Stop'
$runtimeIdentityName = 'id-sac-budget-atlas-runtime-public-pilot'

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
        $headers = @{}
        foreach ($header in $response.Headers) {
            $headers[$header.Key] = $header.Value -join ', '
        }
        foreach ($header in $response.Content.Headers) {
            $headers[$header.Key] = $header.Value -join ', '
        }
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Location = if ($null -ne $response.Headers.Location) { $response.Headers.Location.ToString() } else { '' }
            Headers = $headers
            Body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        }
    }
    catch {
        return [pscustomobject]@{ StatusCode = 0; Location = ''; Headers = @{}; Body = '' }
    }
    finally {
        $client.Dispose()
        $handler.Dispose()
    }
}

function Invoke-InReplica {
    param(
        [Parameter(Mandatory = $true)][string]$RevisionName,
        [Parameter(Mandatory = $true)][string]$ReplicaName,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $raw = & $AzCommand containerapp exec `
        --name $ContainerAppName `
        --resource-group $ResourceGroupName `
        --revision $RevisionName `
        --replica $ReplicaName `
        --command $Command 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Container command failed in revision '$RevisionName'."
    }
    return $raw -join "`n"
}

$app = Invoke-AzJson @(
    'containerapp', 'show', '--name', $ContainerAppName, '--resource-group', $ResourceGroupName, '--output', 'json'
)
$fqdn = [string]$app.properties.configuration.ingress.fqdn
if ([string]::IsNullOrWhiteSpace($fqdn)) {
    throw 'The Container App does not expose an ingress FQDN.'
}

$httpsProbe = Invoke-WebProbe -Uri "https://$fqdn/"
if ([int]$httpsProbe.StatusCode -ne 200) {
    throw "Anonymous HTTPS root returned $($httpsProbe.StatusCode) instead of application content."
}
if ($httpsProbe.Headers.'X-Robots-Tag' -cne 'noindex, nofollow') {
    throw 'Anonymous application responses must include X-Robots-Tag: noindex, nofollow.'
}

$robotsProbe = Invoke-WebProbe -Uri "https://$fqdn/robots.txt"
if ([int]$robotsProbe.StatusCode -ne 200 -or $robotsProbe.Body -notmatch '(?m)^Disallow: /\s*$') {
    throw 'robots.txt must return HTTP 200 and disallow all cooperative crawlers.'
}
if ($robotsProbe.Headers.'X-Robots-Tag' -cne 'noindex, nofollow') {
    throw 'robots.txt must include X-Robots-Tag: noindex, nofollow.'
}

$httpProbe = Invoke-WebProbe -Uri "http://$fqdn/"
if ([int]$httpProbe.StatusCode -eq 200) {
    throw 'Plain HTTP served application content.'
}
if ([int]$httpProbe.StatusCode -ne 0 -and
    @(301, 302, 303, 307, 308) -contains [int]$httpProbe.StatusCode -and
    $httpProbe.Location -notmatch '^https://') {
    throw 'Plain HTTP redirected to a non-HTTPS destination.'
}

if ($app.properties.workloadProfileName -cne 'Consumption') {
    throw 'The public pilot must run on the Consumption workload profile.'
}
if ($app.properties.configuration.activeRevisionsMode -cne 'Single') {
    throw 'Container App revision mode must be Single.'
}
if ($app.properties.configuration.ingress.allowInsecure -ne $false) {
    throw 'Container App ingress must reject insecure traffic.'
}
if ($app.properties.configuration.ingress.stickySessions.affinity -cne 'sticky') {
    throw 'Sticky sessions are not enabled.'
}
if ([int]$app.properties.template.scale.minReplicas -ne 0 -or
    [int]$app.properties.template.scale.maxReplicas -ne 1) {
    throw 'Container App scale must remain exactly zero to one replicas.'
}

$identityIds = @($app.identity.userAssignedIdentities.PSObject.Properties.Name)
if ($identityIds.Count -ne 1 -or $identityIds[0] -notmatch "/$runtimeIdentityName$") {
    throw "The Container App must use only runtime identity '$runtimeIdentityName'."
}
$registries = @($app.properties.configuration.registries)
if ($registries.Count -ne 1 -or
    $registries[0].server -cne 'saccitydaoregistry.azurecr.io' -or
    $registries[0].identity -cne $identityIds[0]) {
    throw 'The Container App must pull from the shared registry through its runtime identity.'
}

$revisions = Invoke-AzJson @(
    'containerapp', 'revision', 'list', '--name', $ContainerAppName,
    '--resource-group', $ResourceGroupName, '--output', 'json'
)
$activeRevisions = @($revisions | Where-Object { $_.properties.active -eq $true })
if ($activeRevisions.Count -ne 1) {
    throw "Expected exactly one active revision, found $($activeRevisions.Count)."
}
$activeRevision = $activeRevisions[0]
$container = @($activeRevision.properties.template.containers | Where-Object { $_.name -ceq 'budget-atlas' })[0]
if ($container.image -notmatch '^saccitydaoregistry\.azurecr\.io/budget-atlas@sha256:[0-9a-f]{64}$') {
    throw 'The active revision does not use an immutable digest from the approved shared registry repository.'
}

$allowedHosts = @($container.env | Where-Object { $_.name -ceq 'APP_ALLOWED_HOSTS' })
if ($allowedHosts.Count -ne 1 -or $allowedHosts[0].value -cne $fqdn) {
    throw 'APP_ALLOWED_HOSTS must exactly equal the Container App FQDN.'
}
$manualRefresh = @($container.env | Where-Object { $_.name -ceq 'BUDGET_MANUAL_REFRESH_ENABLED' })
if ($manualRefresh.Count -ne 1 -or $manualRefresh[0].value -cne '0') {
    throw 'BUDGET_MANUAL_REFRESH_ENABLED must remain 0.'
}
if (@($container.env | Where-Object { $_.name -ceq 'SHINY_TESTMODE' }).Count -ne 0) {
    throw 'SHINY_TESTMODE is forbidden in the Azure deployment.'
}

$replicas = Invoke-AzJson @(
    'containerapp', 'replica', 'list', '--name', $ContainerAppName,
    '--resource-group', $ResourceGroupName, '--revision', $activeRevision.name, '--output', 'json'
)
$replica = @($replicas)[0]
if ($null -eq $replica) {
    throw 'The active revision has no running replica. Run Warm-AzurePublicPilot.ps1 first.'
}

$uid = Invoke-InReplica -RevisionName $activeRevision.name -ReplicaName $replica.name -Command 'id -u'
if ($uid -notmatch '(?m)^\s*10001\s*$') {
    throw 'The application container is not running as UID 10001.'
}
$liveStatus = Invoke-InReplica -RevisionName $activeRevision.name -ReplicaName $replica.name `
    -Command "python -c `"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=5).status)`""
$readyStatus = Invoke-InReplica -RevisionName $activeRevision.name -ReplicaName $replica.name `
    -Command "python -c `"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5).status)`""
if ($liveStatus -notmatch '(?m)^\s*200\s*$' -or $readyStatus -notmatch '(?m)^\s*200\s*$') {
    throw 'Internal liveness and readiness endpoints must both return HTTP 200.'
}

if (-not $BrowserSessionPassed -or $BrowserSessionDurationMinutes -lt 30 -or
    $BrowserSessionRevisionName -cne $activeRevision.name) {
    throw "Record a passing anonymous Shiny WebSocket session of at least 30 minutes for active revision '$($activeRevision.name)' and rerun with matching evidence."
}

Write-Output "Azure public pilot deployment smoke test passed."
Write-Output "Verified the 30-minute anonymous Shiny WebSocket session for revision $($activeRevision.name)."
