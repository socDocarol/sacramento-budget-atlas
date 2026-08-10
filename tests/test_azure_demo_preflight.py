from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Test-AzureDemoPrerequisites.ps1"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is required to exercise the Azure preflight script")
    return executable


def _write_fake_az(
    tmp_path: Path,
    *,
    subscription: str = "Microsoft Azure Enterprise - APPS",
    acr_available: bool = True,
    permissions: list[dict[str, list[str]]] | None = None,
) -> Path:
    fixture = {
        "subscription": subscription,
        "tenant": "City of Sacramento",
        "acrAvailable": acr_available,
        "resourceGroupExists": False,
        "permissions": permissions if permissions is not None else [{"actions": ["*"], "notActions": []}],
        "providers": {
            "Microsoft.App": "NotRegistered",
            "Microsoft.OperationalInsights": "Registered",
            "Microsoft.ContainerRegistry": "Registered",
            "Microsoft.ManagedIdentity": "Registered",
        },
    }
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    fake_az = tmp_path / "fake-az.ps1"
    fake_az.write_text(
        """
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Remaining)
$fixture = Get-Content -Raw $env:AZURE_PREFLIGHT_FIXTURE | ConvertFrom-Json
$command = $Remaining -join ' '
if ($command -match '^version') {
  '{"azure-cli":"2.88.0"}'
  exit 0
}
if ($command -match '^account show') {
  [pscustomobject]@{
    name = $fixture.subscription
    tenantDisplayName = $fixture.tenant
    id = 'subscription-id-must-not-be-printed'
    tenantId = 'tenant-id-must-not-be-printed'
    user = [pscustomobject]@{ name = 'docarol@cityofsacramento.org' }
  } | ConvertTo-Json -Compress
  exit 0
}
if ($command -match '^provider show') {
  $namespaceIndex = [Array]::IndexOf($Remaining, '--namespace') + 1
  $namespace = $Remaining[$namespaceIndex]
  [pscustomobject]@{ namespace = $namespace; registrationState = $fixture.providers.$namespace } |
    ConvertTo-Json -Compress
  exit 0
}
if ($command -match '^rest ') {
  [pscustomobject]@{ value = $fixture.permissions } | ConvertTo-Json -Depth 8 -Compress
  exit 0
}
if ($command -match '^acr check-name') {
  [pscustomobject]@{ nameAvailable = $fixture.acrAvailable } | ConvertTo-Json -Compress
  exit 0
}
if ($command -match '^group exists') {
  if ($fixture.resourceGroupExists) { 'true' } else { 'false' }
  exit 0
}
if ($command -match '^resource list') {
  '[]'
  exit 0
}
Write-Error "Unexpected fake az command: $command"
exit 64
""".strip(),
        encoding="utf-8",
    )
    return fake_az


def _run_preflight(tmp_path: Path, fake_az: Path) -> subprocess.CompletedProcess[str]:
    environment = {"AZURE_PREFLIGHT_FIXTURE": str(tmp_path / "fixture.json")}
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
        env={**__import__("os").environ, **environment},
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _terminal_text(value: str) -> str:
    return " ".join(ANSI_ESCAPE.sub("", value).split())


def test_preflight_reports_read_only_prerequisites_without_identifiers(tmp_path: Path) -> None:
    """A regression that echoes account JSON would expose identifiers in operator logs."""
    result = _run_preflight(tmp_path, _write_fake_az(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "Azure demo preflight passed" in result.stdout
    assert "Microsoft.App: NotRegistered" in result.stdout
    assert "No Azure resources were changed" in result.stdout
    assert "subscription-id-must-not-be-printed" not in result.stdout
    assert "tenant-id-must-not-be-printed" not in result.stdout


def test_preflight_rejects_the_wrong_subscription(tmp_path: Path) -> None:
    """Removing the subscription guard could deploy the experiment into DBA or Shared."""
    result = _run_preflight(tmp_path, _write_fake_az(tmp_path, subscription="Wrong Subscription"))

    assert result.returncode != 0
    assert "Microsoft Azure Enterprise - APPS" in result.stderr


def test_preflight_rejects_missing_deployment_permissions(tmp_path: Path) -> None:
    """Skipping the effective-permissions gate would defer a predictable partial deployment failure."""
    result = _run_preflight(
        tmp_path,
        _write_fake_az(
            tmp_path,
            permissions=[
                {"actions": ["Microsoft.Resources/subscriptions/resourceGroups/read"], "notActions": []}
            ],
        ),
    )

    assert result.returncode != 0
    error = _terminal_text(result.stderr)
    assert "Microsoft.Resources/deployments/validate/action" in error
    assert "Request the necessary Azure role" in error


def test_preflight_rejects_an_unavailable_registry_name(tmp_path: Path) -> None:
    """Removing the global-name check would make the first ACR deployment fail after other resources exist."""
    result = _run_preflight(tmp_path, _write_fake_az(tmp_path, acr_available=False))

    assert result.returncode != 0
    error = _terminal_text(result.stderr)
    assert "sacbudgetatlasdemo" in error
    assert "no longer available" in error
