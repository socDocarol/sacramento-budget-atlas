from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Test-AzurePublicPilotPrerequisites.ps1"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is required to exercise the Azure preflight script")
    return executable


def _write_fake_az(
    tmp_path: Path,
    *,
    subscription: str = "Microsoft Azure Enterprise - DBA",
    permissions: list[dict[str, list[str]]] | None = None,
    profiles: list[dict[str, str]] | None = None,
) -> Path:
    fixture = {
        "subscription": subscription,
        "permissions": permissions if permissions is not None else [{"actions": ["*"], "notActions": []}],
        "profiles": profiles
        if profiles is not None
        else [
            {"name": "Consumption", "workloadProfileType": "Consumption"},
            {"name": "Flex", "workloadProfileType": "Flex"},
        ],
    }
    (tmp_path / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
    fake_az = tmp_path / "fake-az.ps1"
    fake_az.write_text(
        r"""
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Remaining)
$fixture = Get-Content -Raw $env:AZURE_PREFLIGHT_FIXTURE | ConvertFrom-Json
$command = $Remaining -join ' '
Add-Content -LiteralPath $env:AZURE_PREFLIGHT_COMMAND_LOG -Value $command
if ($command -match '^version') { '{"azure-cli":"2.88.0"}'; exit 0 }
if ($command -match '^account show') {
  [pscustomobject]@{
    name = $fixture.subscription
    tenantDisplayName = 'City of Sacramento'
    id = 'subscription-id-must-not-print'
    tenantId = 'tenant-id-must-not-print'
  } | ConvertTo-Json -Compress
  exit 0
}
if ($command -match '^provider show') {
  [pscustomobject]@{ namespace = 'provider'; registrationState = 'Registered' } |
    ConvertTo-Json -Compress
  exit 0
}
if ($command -match '^rest ') {
  [pscustomobject]@{ value = $fixture.permissions } | ConvertTo-Json -Depth 8 -Compress
  exit 0
}
if ($command -match '^containerapp env show') {
  [pscustomobject]@{
    name = 'saccity-shared-env'
    resourceGroup = 'DBA'
    location = 'West US 2'
    id = '/subscriptions/hidden/resourceGroups/DBA/providers/Microsoft.App/managedEnvironments/saccity-shared-env'
    properties = [pscustomobject]@{
      workloadProfiles = $fixture.profiles
      appLogsConfiguration = [pscustomobject]@{ destination = 'log-analytics' }
    }
  } | ConvertTo-Json -Depth 8 -Compress
  exit 0
}
if ($command -match '^acr show') {
  [pscustomobject]@{
    name = 'saccitydaoregistry'
    resourceGroup = 'Databricks'
    loginServer = 'saccitydaoregistry.azurecr.io'
    sku = [pscustomobject]@{ name = 'Basic' }
    anonymousPullEnabled = $false
    publicNetworkAccess = 'Enabled'
  } | ConvertTo-Json -Depth 8 -Compress
  exit 0
}
if ($command -match '^containerapp list') {
  @(
    [pscustomobject]@{ name = 'saccityapps' },
    [pscustomobject]@{ name = 'next311' }
  ) | ConvertTo-Json -Compress
  exit 0
}
Write-Error "Unexpected fake az command: $command"
exit 64
""".strip(),
        encoding="utf-8",
    )
    return fake_az


def _run_preflight(tmp_path: Path, fake_az: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-AzCommand",
            str(fake_az),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "AZURE_PREFLIGHT_FIXTURE": str(tmp_path / "fixture.json"),
            "AZURE_PREFLIGHT_COMMAND_LOG": str(tmp_path / "commands.log"),
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _terminal_text(value: str) -> str:
    return " ".join(ANSI_ESCAPE.sub("", value).replace(" | ", " ").split())


def test_preflight_verifies_shared_resources_without_mutating_them(tmp_path: Path) -> None:
    """A mutating preflight could change the shared environment, registry, or sibling apps."""
    result = _run_preflight(tmp_path, _write_fake_az(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "Azure public pilot preflight passed" in result.stdout
    assert "Consumption workload profile: available" in result.stdout
    assert "Shared logging destination: log-analytics" in result.stdout
    assert "No Azure resources were changed" in result.stdout
    assert "subscription-id-must-not-print" not in result.stdout
    assert "tenant-id-must-not-print" not in result.stdout
    commands = (tmp_path / "commands.log").read_text(encoding="utf-8")
    for mutation in (
        "provider register",
        "deployment create",
        "containerapp update",
        "role assignment create",
    ):
        assert mutation not in commands


def test_preflight_rejects_wrong_subscription(tmp_path: Path) -> None:
    """The subscription guard prevents deploying the pilot back into APPS or another subscription."""
    result = _run_preflight(tmp_path, _write_fake_az(tmp_path, subscription="Wrong Subscription"))

    assert result.returncode != 0
    assert "Microsoft Azure Enterprise - DBA" in _terminal_text(result.stderr)


def test_preflight_requires_consumption_profile(tmp_path: Path) -> None:
    """Deploying without an explicit Consumption profile could place the pilot on Flex capacity."""
    result = _run_preflight(
        tmp_path,
        _write_fake_az(tmp_path, profiles=[{"name": "Flex", "workloadProfileType": "Flex"}]),
    )

    assert result.returncode != 0
    assert "Consumption" in _terminal_text(result.stderr)


def test_preflight_reports_exact_missing_permission(tmp_path: Path) -> None:
    """A vague permission failure would encourage an unnecessarily broad RBAC request."""
    result = _run_preflight(
        tmp_path,
        _write_fake_az(
            tmp_path,
            permissions=[
                {
                    "actions": [
                        "Microsoft.Resources/deployments/validate/action",
                        "Microsoft.Resources/deployments/write",
                        "Microsoft.ManagedIdentity/userAssignedIdentities/write",
                        "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/write",
                        "Microsoft.App/containerApps/write",
                    ],
                    "notActions": [],
                }
            ],
        ),
    )

    assert result.returncode != 0
    error = _terminal_text(result.stderr)
    assert "Microsoft.Authorization/roleAssignments/write" in error
    assert "/resourceGroups/DBA" in error
