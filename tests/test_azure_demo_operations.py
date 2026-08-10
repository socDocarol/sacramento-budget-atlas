from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT / "scripts" / "Test-AzureDemoDeployment.ps1"
WARM_SCRIPT = ROOT / "scripts" / "Warm-AzureDemo.ps1"
FQDN = "ca-sac-budget-atlas-demo.purplepond.westus2.azurecontainerapps.io"
REVISION = "ca-sac-budget-atlas-demo--sha-0123456789ab"


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is required to exercise the Azure operations scripts")
    return executable


def _write_fakes(tmp_path: Path) -> tuple[Path, Path]:
    app = {
        "properties": {
            "latestRevisionName": REVISION,
            "configuration": {
                "activeRevisionsMode": "Single",
                "ingress": {
                    "fqdn": FQDN,
                    "allowInsecure": False,
                    "stickySessions": {"affinity": "sticky"},
                },
            },
            "template": {
                "scale": {"minReplicas": 0, "maxReplicas": 1},
                "containers": [
                    {
                        "name": "budget-atlas",
                        "image": "sacbudgetatlasdemo.azurecr.io/budget-atlas@sha256:" + "a" * 64,
                        "env": [{"name": "APP_ALLOWED_HOSTS", "value": FQDN}],
                    }
                ],
            },
        }
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
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps({"app": app, "revision": revision}), encoding="utf-8")

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
if ($Uri -match '^https://') {
  [pscustomobject]@{ StatusCode = 302; Location = 'https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize' } |
    ConvertTo-Json -Compress
} else {
  [pscustomobject]@{ StatusCode = 301; Location = $Uri -replace '^http:', 'https:' } |
    ConvertTo-Json -Compress
}
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


def test_deployment_smoke_test_enforces_runtime_and_browser_evidence(tmp_path: Path) -> None:
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
    assert "Azure demo deployment smoke test passed" in result.stdout
    assert "30-minute authenticated browser session" in result.stdout


def test_warm_script_reaches_internal_readiness(tmp_path: Path) -> None:
    result = _run(tmp_path, WARM_SCRIPT, [])

    assert result.returncode == 0, result.stderr
    assert FQDN in result.stdout
    assert "ready" in result.stdout.lower()
