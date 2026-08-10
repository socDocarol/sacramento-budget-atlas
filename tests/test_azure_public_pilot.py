from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_identity_bootstrap_reuses_shared_dba_platform() -> None:
    """Creating a platform resource here could overwrite shared DBA configuration."""
    main = _read("infra/main.bicep")
    identities = _read("infra/modules/identities.bicep")
    parameters = _read("infra/parameters/public-pilot.bicepparam")
    assert "targetScope = 'subscription'" in main
    assert "resource dbaResourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' existing" in main
    assert "resource registryResourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' existing" in main
    assert "module identities './modules/identities.bicep'" in main
    registry_access = _read("infra/modules/registry-access.bicep")
    deployment = "\n".join((main, identities, registry_access))

    assert "scope: dbaResourceGroup" in main
    assert "scope: registryResourceGroup" in main
    assert "resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' existing" in identities
    assert "resource registry 'Microsoft.ContainerRegistry/registries@" in registry_access
    assert "existing =" in registry_access
    assert "registryResourceGroupName = 'Databricks'" in parameters
    assert "registryName = 'saccitydaoregistry'" in parameters
    assert "containerAppsEnvironmentName = 'saccity-shared-env'" in parameters
    assert "githubFederatedSubject = 'repo:socDocarol/sacramento-budget-atlas:environment:azure-public-pilot'" in parameters

    forbidden_created_types = (
        "Microsoft.Resources/resourceGroups@2025-04-01' = {",
        "Microsoft.OperationalInsights/workspaces@",
        "Microsoft.ContainerRegistry/registries@2025-11-01' = {",
        "Microsoft.Consumption/budgets@",
    )
    for resource_type in forbidden_created_types:
        assert resource_type not in deployment


def test_identity_bootstrap_scopes_registry_roles_to_separate_identities() -> None:
    """Combining runtime and deployment permissions would violate the pilot trust boundary."""
    identities = _read("infra/modules/identities.bicep")
    registry_access = _read("infra/modules/registry-access.bicep")
    parameters = _read("infra/parameters/public-pilot.bicepparam")

    assert "runtimeAcrPull" in registry_access
    assert "githubAcrPush" in registry_access
    assert "scope: registry" in registry_access
    assert "7f951dda-4ed3-4680-a7ca-43fe172d538d" in registry_access
    assert "8311e382-0749-4cb8-b61a-304f252e45ec" in registry_access
    assert "id-sac-budget-atlas-runtime-public-pilot" in parameters
    assert "id-sac-budget-atlas-github-public-pilot" in parameters
    assert "Container Apps Contributor" not in registry_access
    assert "358470bc-b998-42bd-ab17-a7e34c199c0f" not in registry_access


def test_public_pilot_parameters_do_not_embed_account_identifiers() -> None:
    """Committing tenant or subscription IDs would make the reusable template account-specific."""
    parameters = _read("infra/parameters/public-pilot.bicepparam")

    assert "subscriptionId" not in parameters
    assert "tenantId" not in parameters
    assert "5307de98-bb54-4d1e-9ccc-d1cafbe8e3e1" not in parameters
    assert "ba834b27-3286-40b8-a78c-cb233b85bfdb" not in parameters
    assert "expiresOn: '2026-09-30'" in parameters
