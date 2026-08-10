using '../app.bicep'

param containerAppsEnvironmentName = 'saccity-shared-env'
param registryResourceGroupName = 'Databricks'
param registryName = 'saccitydaoregistry'
param runtimeIdentityName = 'id-sac-budget-atlas-runtime-public-pilot'
param githubIdentityName = 'id-sac-budget-atlas-github-public-pilot'
param containerAppName = 'ca-sac-budget-atlas-public-pilot'
param imageDigestReference = readEnvironmentVariable('BUDGET_ATLAS_IMAGE_DIGEST')
param revisionSuffix = readEnvironmentVariable('BUDGET_ATLAS_REVISION_SUFFIX')
param containerMemory = '1Gi'
param tags = {
  workload: 'SacramentoBudgetAtlas'
  environment: 'public-pilot'
  lifecycle: 'experimental'
  owner: 'docarol@cityofsacramento.org'
  dataClassification: 'public-source-public-app'
  expiresOn: '2026-09-30'
}
