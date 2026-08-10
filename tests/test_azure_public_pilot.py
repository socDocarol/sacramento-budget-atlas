from __future__ import annotations

import re
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
    assert (
        "resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' existing"
        in identities
    )
    assert "resource registry 'Microsoft.ContainerRegistry/registries@" in registry_access
    assert "existing =" in registry_access
    assert "registryResourceGroupName = 'Databricks'" in parameters
    assert "registryName = 'saccitydaoregistry'" in parameters
    assert "containerAppsEnvironmentName = 'saccity-shared-env'" in parameters
    assert (
        "githubFederatedSubject = 'repo:socDocarol/sacramento-budget-atlas:environment:azure-public-pilot'"
        in parameters
    )

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
    assert re.search(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", parameters, re.IGNORECASE) is None
    assert "expiresOn: '2026-09-30'" in parameters


def test_container_app_is_anonymous_on_the_consumption_profile() -> None:
    """Retaining Entra auth or omitting the profile would implement the wrong pilot route."""
    app = _read("infra/app.bicep")
    parameters = _read("infra/parameters/app-public-pilot.bicepparam")
    combined = "\n".join((app, parameters)).lower()

    assert "param containerAppName string = 'ca-sac-budget-atlas-public-pilot'" in app
    assert "workloadProfileName: 'Consumption'" in app
    assert "activeRevisionsMode: 'Single'" in app
    assert "allowInsecure: false" in app
    assert "affinity: 'sticky'" in app
    assert "minReplicas: 0" in app
    assert "maxReplicas: 1" in app
    assert "BUDGET_MANUAL_REFRESH_ENABLED" in app
    assert "value: '0'" in app
    assert "authconfigs" not in combined
    assert "entraclient" not in combined
    assert "clientsecret" not in combined
    assert "secrets:" not in combined


def test_container_app_uses_existing_shared_resources_and_runtime_identity() -> None:
    """Creating or password-authenticating shared dependencies would bypass the hardened boundary."""
    app = _read("infra/app.bicep")
    parameters = _read("infra/parameters/app-public-pilot.bicepparam")

    assert "resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' existing" in app
    assert "resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing" in app
    assert "scope: resourceGroup(registryResourceGroupName)" in app
    assert (
        "resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing"
        in app
    )
    assert "identity: runtimeIdentity.id" in app
    assert "registryResourceGroupName = 'Databricks'" in parameters
    assert "registryName = 'saccitydaoregistry'" in parameters
    assert "containerAppsEnvironmentName = 'saccity-shared-env'" in parameters
    assert "runtimeIdentityName = 'id-sac-budget-atlas-runtime-public-pilot'" in parameters


def test_container_app_enforces_immutable_release_and_health_contract() -> None:
    """A mutable image or missing probe could route traffic to an unverified revision."""
    app = _read("infra/app.bicep")

    assert "contains(imageDigestReference, '@sha256:')" in app
    assert "type: 'Startup'" in app
    assert "type: 'Liveness'" in app
    assert "type: 'Readiness'" in app
    assert app.count("path: '/health/live'") == 2
    assert app.count("path: '/health/ready'") == 1
    assert "name: 'APP_ALLOWED_HOSTS'" in app
    assert "'${containerAppName}.${containerAppsEnvironment.properties.defaultDomain}'" in app


def test_github_deployment_role_is_scoped_to_the_new_container_app() -> None:
    """Resource-group deployment rights could permit changing Measure U or another shared app."""
    app = _read("infra/app.bicep")
    parameters = _read("infra/parameters/app-public-pilot.bicepparam")

    assert "358470bc-b998-42bd-ab17-a7e34c199c0f" in app
    assert "resource githubContainerAppsContributor" in app
    assert "scope: containerApp" in app
    assert "principalId: githubIdentity.properties.principalId" in app
    assert "githubIdentityName = 'id-sac-budget-atlas-github-public-pilot'" in parameters


def test_public_pilot_workflow_builds_scans_and_updates_only_the_pilot_app() -> None:
    """A wrong workflow target could update a shared sibling app or deploy an unscanned image."""
    workflow = _read(".github/workflows/deploy-azure-public-pilot.yml")

    assert "environment: azure-public-pilot" in workflow
    assert "id-token: write" in workflow
    assert "ACR_NAME: saccitydaoregistry" in workflow
    assert "ACR_LOGIN_SERVER: saccitydaoregistry.azurecr.io" in workflow
    assert "resource_group='DBA'" in workflow
    assert "app_name='ca-sac-budget-atlas-public-pilot'" in workflow
    assert "az containerapp update" in workflow
    assert '--image "${{ steps.push.outputs.digest_reference }}"' in workflow
    assert "anchore/sbom-action@" in workflow
    assert "aquasecurity/trivy-action@" in workflow
    assert "azure/login@" in workflow
    assert "client-secret" not in workflow.lower()
    assert "publish-profile" not in workflow.lower()
    assert "saccityapps" not in workflow
    assert "next311" not in workflow


def test_resource_profile_runs_on_the_public_pilot_branch() -> None:
    """Leaving the old branch selector would silently skip the sizing gate for pilot changes."""
    workflow = _read(".github/workflows/ci.yml")

    assert "refs/heads/feat/azure-container-apps-public-pilot" in workflow
    assert "refs/heads/feat/azure-container-apps-demo" not in workflow


def test_operator_docs_describe_shared_public_pilot_without_publishing_url() -> None:
    """Stale authenticated-demo instructions could send an operator down the hardened route."""
    infra_readme = _read("infra/README.md")
    hardening = _read("docs/azure-deployment-hardening.md")
    runbook = _read("docs/azure-container-apps-public-pilot-runbook.md")
    combined = "\n".join((infra_readme, hardening, runbook))

    assert "Microsoft Azure Enterprise - DBA" in combined
    assert "saccity-shared-env" in combined
    assert "saccitydaoregistry" in combined
    assert "Consumption" in combined
    assert "azure-public-pilot" in combined
    assert "anonymous" in combined.lower()
    assert "X-Robots-Tag" in combined
    assert "Search exclusion is not access control" in combined
    assert "2026-09-30" in combined
    assert "Test-AzurePublicPilotPrerequisites.ps1" in combined
    assert "Warm-AzurePublicPilot.ps1" in combined
    assert "Test-AzurePublicPilotDeployment.ps1" in combined
    assert "az deployment sub what-if" in runbook
    assert "az deployment group what-if" in runbook
    assert "Microsoft.Authorization/roleAssignments/write" in runbook
    assert "known-good immutable digest" in runbook

    stale_active_instructions = (
        "Microsoft Azure Enterprise - APPS",
        "rg-sac-budget-atlas-demo-wus2",
        "sacbudgetatlasdemo",
        "Budget Atlas Demo Users",
        "Initialize-AzureDemoIdentity.ps1",
    )
    for stale_instruction in stale_active_instructions:
        assert stale_instruction not in combined
    assert "azurecontainerapps.io" not in combined
