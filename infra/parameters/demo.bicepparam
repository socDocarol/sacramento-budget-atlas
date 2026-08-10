using '../main.bicep'

param location = 'westus2'
param resourceGroupName = 'rg-sac-budget-atlas-demo-wus2'
param logAnalyticsWorkspaceName = 'log-sac-budget-atlas-demo-wus2'
param containerAppsEnvironmentName = 'cae-sac-budget-atlas-demo-wus2'
param registryName = 'sacbudgetatlasdemo'
param runtimeIdentityName = 'id-sac-budget-atlas-runtime-demo'
param githubIdentityName = 'id-sac-budget-atlas-github-demo'
param githubFederatedSubject = 'repo:socDocarol/sacramento-budget-atlas:environment:azure-demo'
param tags = {
  workload: 'SacramentoBudgetAtlas'
  environment: 'demo'
  lifecycle: 'experimental'
  owner: 'docarol@cityofsacramento.org'
  dataClassification: 'public-source-internal-app'
  expiresOn: '2026-09-30'
}
