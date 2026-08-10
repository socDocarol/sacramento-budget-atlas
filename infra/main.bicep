targetScope = 'subscription'

@description('Azure region for every demo resource.')
param location string

@description('Dedicated resource group for the disposable demo.')
param resourceGroupName string

@description('Log Analytics workspace name.')
param logAnalyticsWorkspaceName string

@description('Container Apps managed environment name.')
param containerAppsEnvironmentName string

@description('Globally unique Azure Container Registry name.')
param registryName string

@description('User-assigned identity used by the Container App at runtime.')
param runtimeIdentityName string

@description('User-assigned identity federated to the GitHub deployment environment.')
param githubIdentityName string

@description('GitHub Actions OIDC subject for the protected deployment environment.')
param githubFederatedSubject string

@description('Governance tags applied to all supported resources.')
param tags object

resource demoResourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module platform './modules/platform.bicep' = {
  name: 'budget-atlas-demo-platform'
  scope: demoResourceGroup
  params: {
    location: location
    logAnalyticsWorkspaceName: logAnalyticsWorkspaceName
    containerAppsEnvironmentName: containerAppsEnvironmentName
    registryName: registryName
    runtimeIdentityName: runtimeIdentityName
    githubIdentityName: githubIdentityName
    githubFederatedSubject: githubFederatedSubject
    tags: tags
  }
}

output resourceGroupName string = demoResourceGroup.name
output containerAppsEnvironmentId string = platform.outputs.containerAppsEnvironmentId
output containerAppsDefaultDomain string = platform.outputs.containerAppsDefaultDomain
output registryName string = platform.outputs.registryName
output registryLoginServer string = platform.outputs.registryLoginServer
output runtimeIdentityId string = platform.outputs.runtimeIdentityId
output githubIdentityClientId string = platform.outputs.githubIdentityClientId
