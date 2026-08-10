targetScope = 'resourceGroup'

@description('Existing shared Azure Container Registry name in the deployment resource group.')
param registryName string

@description('Resource ID of the pilot runtime identity.')
param runtimeIdentityId string

@description('Principal ID of the pilot runtime identity.')
param runtimeIdentityPrincipalId string

@description('Resource ID of the pilot GitHub deployment identity.')
param githubIdentityId string

@description('Principal ID of the pilot GitHub deployment identity.')
param githubIdentityPrincipalId string

var acrPullRoleDefinitionId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var acrPushRoleDefinitionId = '8311e382-0749-4cb8-b61a-304f252e45ec'

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: registryName
}

resource runtimeAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, runtimeIdentityId, acrPullRoleDefinitionId)
  scope: registry
  properties: {
    principalId: runtimeIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      acrPullRoleDefinitionId
    )
  }
}

resource githubAcrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, githubIdentityId, acrPushRoleDefinitionId)
  scope: registry
  properties: {
    principalId: githubIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      acrPushRoleDefinitionId
    )
  }
}

output registryId string = registry.id
output registryLoginServer string = registry.properties.loginServer
