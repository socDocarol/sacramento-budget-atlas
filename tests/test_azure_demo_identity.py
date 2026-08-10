from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Initialize-AzureDemoIdentity.ps1"
DOMAIN = "purplepond-01234567.westus2.azurecontainerapps.io"


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is required to exercise the Entra bootstrap script")
    return executable


def _write_fake_az(
    tmp_path: Path,
    *,
    apps: list[dict[str, object]] | None = None,
    service_principals: list[dict[str, object]] | None = None,
    groups: list[dict[str, object]] | None = None,
) -> Path:
    fixture = {
        "apps": apps if apps is not None else [],
        "servicePrincipals": service_principals if service_principals is not None else [],
        "groups": groups
        if groups is not None
        else [{"id": "group-object-id", "displayName": "Budget Atlas Demo Users", "securityEnabled": True}],
    }
    (tmp_path / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
    fake_az = tmp_path / "fake-az.ps1"
    fake_az.write_text(
        r"""
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Remaining)
$fixture = Get-Content -Raw $env:AZURE_IDENTITY_FIXTURE | ConvertFrom-Json
$command = $Remaining -join ' '
Add-Content -LiteralPath $env:AZURE_IDENTITY_COMMAND_LOG -Value $command
if ($command -match '^ad app list') { ConvertTo-Json -InputObject @($fixture.apps) -Depth 8 -Compress; exit 0 }
if ($command -match '^ad app create') {
  [pscustomobject]@{ id = 'app-object-id'; appId = 'client-id'; passwordCredentials = @() } |
    ConvertTo-Json -Depth 8 -Compress
  exit 0
}
if ($command -match '^ad app update') { '{}'; exit 0 }
if ($command -match '^ad sp list') {
  ConvertTo-Json -InputObject @($fixture.servicePrincipals) -Depth 8 -Compress
  exit 0
}
if ($command -match '^ad sp create') {
  [pscustomobject]@{ id = 'sp-object-id'; appId = 'client-id'; appRoleAssignmentRequired = $false } |
    ConvertTo-Json -Compress
  exit 0
}
if ($command -match '^ad group list') {
  ConvertTo-Json -InputObject @($fixture.groups) -Depth 8 -Compress
  exit 0
}
if ($command -match '^ad app credential reset') {
  [pscustomobject]@{ appId = 'client-id'; password = 'generated-secret-must-not-print' } |
    ConvertTo-Json -Compress
  exit 0
}
if ($command -match '^rest .*method GET') { '{"value":[]}'; exit 0 }
if ($command -match '^rest .*method (PATCH|POST)') { '{}'; exit 0 }
Write-Error "Unexpected fake az command: $command"
exit 64
""".strip(),
        encoding="utf-8",
    )
    return fake_az


def _run_identity(tmp_path: Path, fake_az: Path, *, what_if: bool) -> subprocess.CompletedProcess[str]:
    command = [
        _powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        "-ContainerAppsDefaultDomain",
        DOMAIN,
        "-AzCommand",
        str(fake_az),
    ]
    if what_if:
        command.append("-WhatIf")
    return subprocess.run(
        command,
        cwd=ROOT,
        env={
            **os.environ,
            "AZURE_IDENTITY_FIXTURE": str(tmp_path / "fixture.json"),
            "AZURE_IDENTITY_COMMAND_LOG": str(tmp_path / "commands.log"),
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_identity_dry_run_reports_callback_without_mutations(tmp_path: Path) -> None:
    fake_az = _write_fake_az(
        tmp_path,
        apps=[{"id": "app-object-id", "appId": "client-id", "passwordCredentials": []}],
        service_principals=[{"id": "sp-object-id", "appId": "client-id"}],
    )

    result = _run_identity(tmp_path, fake_az, what_if=True)

    assert result.returncode == 0, result.stderr
    assert f"https://ca-sac-budget-atlas-demo.{DOMAIN}/.auth/login/aad/callback" in result.stdout
    commands = (tmp_path / "commands.log").read_text(encoding="utf-8")
    for mutation in (
        "app create",
        "app update",
        "sp create",
        "method PATCH",
        "method POST",
        "credential reset",
    ):
        assert mutation not in commands


def test_identity_dry_run_requires_the_access_group(tmp_path: Path) -> None:
    result = _run_identity(tmp_path, _write_fake_az(tmp_path, groups=[]), what_if=True)

    assert result.returncode != 0
    assert "identity administrator" in result.stderr.lower()
    assert "Budget Atlas Demo Users" in result.stderr


def test_identity_bootstrap_configures_first_run_without_printing_secret(tmp_path: Path) -> None:
    result = _run_identity(tmp_path, _write_fake_az(tmp_path), what_if=False)

    assert result.returncode == 0, result.stderr
    combined_output = result.stdout + result.stderr
    assert "generated-secret-must-not-print" not in combined_output
    assert "client-id" in result.stdout
    commands = (tmp_path / "commands.log").read_text(encoding="utf-8")
    for mutation in ("app create", "sp create", "method PATCH", "method POST", "credential reset"):
        assert mutation in commands
