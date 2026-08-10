from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT / "scripts" / "Test-AzurePublicPilotDeployment.ps1"
WARM_SCRIPT = ROOT / "scripts" / "Warm-AzurePublicPilot.ps1"
FQDN = "ca-sac-budget-atlas-public-pilot.example.westus2.azurecontainerapps.io"
REVISION = "ca-sac-budget-atlas-public-pilot--sha-0123456789ab"
RUNTIME_IDENTITY = "/subscriptions/hidden/resourceGroups/DBA/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-sac-budget-atlas-runtime-public-pilot"


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is required to exercise Azure operations scripts")
    return executable


def _write_fakes(tmp_path: Path) -> tuple[Path, Path]:
    container = {
        "name": "budget-atlas",
        "image": "saccitydaoregistry.azurecr.io/budget-atlas@sha256:" + "a" * 64,
        "env": [
            {"name": "APP_ALLOWED_HOSTS", "value": FQDN},
            {"name": "BUDGET_MANUAL_REFRESH_ENABLED", "value": "0"},
        ],
    }
    app = {
        "identity": {"type": "UserAssigned", "userAssignedIdentities": {RUNTIME_IDENTITY: {}}},
        "properties": {
            "latestRevisionName": REVISION,
            "workloadProfileName": "Consumption",
            "configuration": {
                "activeRevisionsMode": "Single",
                "ingress": {
                    "fqdn": FQDN,
                    "allowInsecure": False,
                    "stickySessions": {"affinity": "sticky"},
                },
                "registries": [
                    {
                        "server": "saccitydaoregistry.azurecr.io",
                        # Azure resource IDs are case-insensitive and live API responses
                        # do not preserve casing consistently across these two fields.
                        "identity": RUNTIME_IDENTITY.upper(),
                    }
                ],
            },
            "template": {
                "scale": {"minReplicas": 0, "maxReplicas": 1},
                "containers": [container],
            },
        },
    }
    revision = {
        "name": REVISION,
        "properties": {
            "active": True,
            "healthState": "Healthy",
            "provisioningState": "Provisioned",
            "template": app["properties"]["template"],
        },
    }
    (tmp_path / "fixture.json").write_text(json.dumps({"app": app, "revision": revision}), encoding="utf-8")

    fake_az = tmp_path / "fake-az.ps1"
    fake_az.write_text(
        r"""
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Remaining)
$fixture = Get-Content -Raw $env:AZURE_OPERATIONS_FIXTURE | ConvertFrom-Json
$command = $Remaining -join ' '
if ($command -match '^containerapp show') { $fixture.app | ConvertTo-Json -Depth 20 -Compress; exit 0 }
if ($command -match '^containerapp revision list') {
  ConvertTo-Json -InputObject @($fixture.revision) -Depth 20 -Compress
  exit 0
}
if ($command -match '^containerapp replica list') {
  ConvertTo-Json -InputObject @([pscustomobject]@{ name = 'replica-one' }) -Compress
  exit 0
}
if ($command -match '^containerapp exec') {
  Write-Error 'WARNING: Use ctrl + D to exit.' -ErrorAction Continue
  if ($command -match '[\"]') {
    Write-Error 'Nested double quotes are not portable through az.cmd.'
    exit 65
  }
  if ($command -match 'id -u') { '10001' } else { '200' }
  exit 0
}
Write-Error "Unexpected fake az command: $command"
exit 64
""".strip(),
        encoding="utf-8",
    )

    fake_web = tmp_path / "fake-web.ps1"
    fake_web.write_text(
        r"""
param([string]$Uri)
if ($Uri -match '^http://') {
  [pscustomobject]@{ StatusCode = 301; Location = $Uri -replace '^http:', 'https:'; Headers = @{}; Body = '' } |
    ConvertTo-Json -Compress
  exit 0
}
if ($Uri -match '/robots.txt$') {
  [pscustomobject]@{
    StatusCode = 200
    Location = ''
    Headers = @{ 'X-Robots-Tag' = 'noindex, nofollow' }
    Body = "User-agent: *`nDisallow: /`n"
  } | ConvertTo-Json -Compress
  exit 0
}
[pscustomobject]@{
  StatusCode = 200
  Location = ''
  Headers = @{ 'X-Robots-Tag' = 'noindex, nofollow' }
  Body = '<html>Budget Atlas</html>'
} | ConvertTo-Json -Compress
""".strip(),
        encoding="utf-8",
    )
    return fake_az, fake_web


def _run(tmp_path: Path, script: Path, extra: list[str]) -> subprocess.CompletedProcess[str]:
    fake_az, fake_web = _write_fakes(tmp_path)
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-AzCommand",
            str(fake_az),
            "-WebProbeCommand",
            str(fake_web),
            *extra,
        ],
        cwd=ROOT,
        env={**os.environ, "AZURE_OPERATIONS_FIXTURE": str(tmp_path / "fixture.json")},
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_deployment_smoke_test_enforces_public_runtime_and_session_evidence(tmp_path: Path) -> None:
    """A green smoke test must prove anonymous access without relaxing the runtime boundary."""
    result = _run(
        tmp_path,
        SMOKE_SCRIPT,
        [
            "-BrowserSessionRevisionName",
            REVISION,
            "-BrowserSessionDurationMinutes",
            "30",
            "-BrowserSessionPassed",
        ],
    )

    assert result.returncode == 0, result.stderr
    assert "Azure public pilot deployment smoke test passed" in result.stdout
    assert "30-minute anonymous Shiny WebSocket session" in result.stdout


def test_warm_script_reaches_internal_readiness(tmp_path: Path) -> None:
    result = _run(tmp_path, WARM_SCRIPT, [])

    assert result.returncode == 0, result.stderr
    assert FQDN in result.stdout
    assert "ready" in result.stdout.lower()


@pytest.mark.parametrize("script", [SMOKE_SCRIPT, WARM_SCRIPT])
def test_container_exec_tolerates_azure_cli_stderr_warnings(script: Path) -> None:
    """PowerShell 5.1 must not turn az containerapp exec's normal warning into failure."""
    source = script.read_text(encoding="utf-8")

    assert "$ErrorActionPreference = 'Continue'" in source
    assert "$execExitCode = $LASTEXITCODE" in source
