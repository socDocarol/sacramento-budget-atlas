using '../main.bicep'

param location = 'westus2'
param dbaResourceGroupName = 'DBA'
param containerAppsEnvironmentName = 'saccity-shared-env'
param registryResourceGroupName = 'Databricks'
param registryName = 'saccitydaoregistry'
param runtimeIdentityName = 'id-sac-budget-atlas-runtime-public-pilot'
param githubIdentityName = 'id-sac-budget-atlas-github-public-pilot'
param githubFederatedSubject = 'repo:socDocarol/sacramento-budget-atlas:environment:azure-public-pilot'
param tags = {
  workload: 'SacramentoBudgetAtlas'
  environment: 'public-pilot'
  lifecycle: 'experimental'
  owner: 'docarol@cityofsacramento.org'
  dataClassification: 'public-source-public-app'
  expiresOn: '2026-09-30'
}
