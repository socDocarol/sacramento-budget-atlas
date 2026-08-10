using '../app.bicep'

param containerAppsEnvironmentName = 'cae-sac-budget-atlas-demo-wus2'
param registryName = 'sacbudgetatlasdemo'
param runtimeIdentityName = 'id-sac-budget-atlas-runtime-demo'
param containerAppName = 'ca-sac-budget-atlas-demo'
param imageDigestReference = readEnvironmentVariable('BUDGET_ATLAS_IMAGE_DIGEST')
param revisionSuffix = readEnvironmentVariable('BUDGET_ATLAS_REVISION_SUFFIX')
param entraClientId = readEnvironmentVariable('BUDGET_ATLAS_ENTRA_CLIENT_ID')
param entraClientSecret = readEnvironmentVariable('BUDGET_ATLAS_ENTRA_CLIENT_SECRET')
param containerMemory = '1Gi'
param tags = {
  workload: 'SacramentoBudgetAtlas'
  environment: 'demo'
  lifecycle: 'experimental'
  owner: 'docarol@cityofsacramento.org'
  dataClassification: 'public-source-internal-app'
  expiresOn: '2026-09-30'
}
