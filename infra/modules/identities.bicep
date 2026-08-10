targetScope = 'resourceGroup'

@description('Azure region for pilot-owned identities.')
param location string

@description('Existing shared Container Apps managed environment name in the deployment resource group.')
param containerAppsEnvironmentName string

param runtimeIdentityName string
param githubIdentityName string
param githubFederatedSubject string
param tags object

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: containerAppsEnvironmentName
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: runtimeIdentityName
  location: location
  tags: tags
}

resource githubIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: githubIdentityName
  location: location
  tags: tags
}

resource githubFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  parent: githubIdentity
  name: 'github-azure-public-pilot'
  properties: {
    audiences: [
      'api://AzureADTokenExchange'
    ]
    issuer: 'https://token.actions.githubusercontent.com'
    subject: githubFederatedSubject
  }
}

output containerAppsEnvironmentId string = containerAppsEnvironment.id
output containerAppsDefaultDomain string = containerAppsEnvironment.properties.defaultDomain
output runtimeIdentityId string = runtimeIdentity.id
output runtimeIdentityPrincipalId string = runtimeIdentity.properties.principalId
output githubIdentityId string = githubIdentity.id
output githubIdentityClientId string = githubIdentity.properties.clientId
output githubIdentityPrincipalId string = githubIdentity.properties.principalId
