targetScope = 'resourceGroup'

@description('Container Apps managed environment name from the foundation deployment.')
param containerAppsEnvironmentName string

@description('Azure Container Registry name from the foundation deployment.')
param registryName string

@description('Runtime user-assigned identity name from the foundation deployment.')
param runtimeIdentityName string

@description('Container App name.')
param containerAppName string = 'ca-sac-budget-atlas-demo'

@description('Immutable ACR image reference, including its SHA-256 manifest digest.')
param imageDigestReference string

@description('Revision suffix formed from sha- and 12 lowercase hexadecimal commit characters.')
@minLength(16)
@maxLength(16)
param revisionSuffix string

@description('Microsoft Entra application client ID.')
@minLength(1)
param entraClientId string

@description('Short-lived Microsoft Entra client secret used only by Container Apps authentication.')
@secure()
param entraClientSecret string

@description('Memory allocation proven by the constrained resource profile.')
@allowed([
  '1Gi'
  '2Gi'
])
param containerMemory string = '1Gi'

@description('Governance tags applied to the Container App.')
param tags object

var revisionCommit = substring(revisionSuffix, 4, 12)
var revisionCharacters = map(range(0, 12), index => substring(revisionCommit, index, 1))
var revisionIsLowercaseHex = length(filter(
  revisionCharacters,
  character => contains('0123456789abcdef', character)
)) == 12
var validatedImageDigestReference = contains(imageDigestReference, '@sha256:')
  ? imageDigestReference
  : fail('imageDigestReference must contain @sha256:.')
var validatedRevisionSuffix = startsWith(revisionSuffix, 'sha-') && revisionIsLowercaseHex
  ? revisionSuffix
  : fail('revisionSuffix must be sha- followed by 12 lowercase hexadecimal characters.')

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: containerAppsEnvironmentName
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: registryName
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: runtimeIdentityName
}

resource containerApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: containerAppName
  location: resourceGroup().location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${runtimeIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      maxInactiveRevisions: 5
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8000
        transport: 'auto'
        stickySessions: {
          affinity: 'sticky'
        }
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: runtimeIdentity.id
        }
      ]
      secrets: [
        {
          name: 'entra-client-secret'
          value: entraClientSecret
        }
      ]
    }
    template: {
      revisionSuffix: validatedRevisionSuffix
      terminationGracePeriodSeconds: 30
      containers: [
        {
          name: 'budget-atlas'
          image: validatedImageDigestReference
          env: [
            {
              name: 'BUDGET_ARCGIS_URL'
              value: 'https://services5.arcgis.com/54falWtcpty3V47Z/arcgis/rest/services/City_of_Sacramento_Approved_Budgets/FeatureServer/0'
            }
            {
              name: 'BUDGET_CACHE_DIR'
              value: '/var/cache/sacramento-budget'
            }
            {
              name: 'BUDGET_CACHE_TTL_SECONDS'
              value: '86400'
            }
            {
              name: 'BUDGET_PREPARED_SCHEMA_VERSION'
              value: '1'
            }
            {
              name: 'BUDGET_BACKGROUND_REFRESH_ENABLED'
              value: '1'
            }
            {
              name: 'BUDGET_MANUAL_REFRESH_ENABLED'
              value: '0'
            }
            {
              name: 'BUDGET_MANUAL_REFRESH_COOLDOWN_SECONDS'
              value: '300'
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
            {
              name: 'APP_BASE_PATH'
              value: '/'
            }
            {
              name: 'APP_ALLOWED_HOSTS'
              value: '${containerAppName}.${containerAppsEnvironment.properties.defaultDomain}'
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: containerMemory
          }
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health/live'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 10
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health/live'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health/ready'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        pollingInterval: 30
        cooldownPeriod: 300
        rules: [
          {
            name: 'http'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

resource authentication 'Microsoft.App/containerApps/authConfigs@2025-01-01' = {
  parent: containerApp
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
    }
    httpSettings: {
      requireHttps: true
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: entraClientId
          clientSecretSettingName: 'entra-client-secret'
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
      }
    }
    login: {
      tokenStore: {
        enabled: false
      }
    }
  }
}

output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output revisionName string = containerApp.properties.latestRevisionName
output authenticationResourceId string = authentication.id
