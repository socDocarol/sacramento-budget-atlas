targetScope = 'subscription'

@description('Azure region for the two pilot-owned managed identities.')
param location string

@description('Existing resource group that owns the shared Container Apps environment.')
param dbaResourceGroupName string

@description('Existing shared Container Apps managed environment name.')
param containerAppsEnvironmentName string

@description('Existing resource group that owns the shared registry.')
param registryResourceGroupName string

@description('Existing shared Azure Container Registry name.')
param registryName string

@description('User-assigned identity used by the Container App at runtime.')
param runtimeIdentityName string

@description('User-assigned identity federated to the GitHub deployment environment.')
param githubIdentityName string

@description('GitHub Actions OIDC subject for the protected deployment environment.')
param githubFederatedSubject string

@description('Governance tags applied only to pilot-owned resources.')
param tags object

resource dbaResourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' existing = {
  name: dbaResourceGroupName
}

resource registryResourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' existing = {
  name: registryResourceGroupName
}

module identities './modules/identities.bicep' = {
  name: 'budget-atlas-public-pilot-identities'
  scope: dbaResourceGroup
  params: {
    location: location
    containerAppsEnvironmentName: containerAppsEnvironmentName
    runtimeIdentityName: runtimeIdentityName
    githubIdentityName: githubIdentityName
    githubFederatedSubject: githubFederatedSubject
    tags: tags
  }
}

module registryAccess './modules/registry-access.bicep' = {
  name: 'budget-atlas-public-pilot-registry-access'
  scope: registryResourceGroup
  params: {
    registryName: registryName
    runtimeIdentityId: identities.outputs.runtimeIdentityId
    runtimeIdentityPrincipalId: identities.outputs.runtimeIdentityPrincipalId
    githubIdentityId: identities.outputs.githubIdentityId
    githubIdentityPrincipalId: identities.outputs.githubIdentityPrincipalId
  }
}

output containerAppsEnvironmentId string = identities.outputs.containerAppsEnvironmentId
output containerAppsDefaultDomain string = identities.outputs.containerAppsDefaultDomain
output registryId string = registryAccess.outputs.registryId
output registryLoginServer string = registryAccess.outputs.registryLoginServer
output runtimeIdentityId string = identities.outputs.runtimeIdentityId
output githubIdentityClientId string = identities.outputs.githubIdentityClientId
output githubIdentityPrincipalId string = identities.outputs.githubIdentityPrincipalId
