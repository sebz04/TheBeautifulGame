// MatchMind on Azure (TASK-24). One resource group with the app and its data; a role on the
// existing Foundry resource for the app's identity; a subscription budget with alerts.
targetScope = 'subscription'

@minLength(1)
@maxLength(32)
@description('azd environment name; names the resource group (rg-<name>).')
param environmentName string

@description('Azure for Students allows only a few regions: North Central US is one.')
param location string

@description('Object id of the person deploying (Azure SQL admin, blob uploads). Set by azd.')
param principalId string

@description('Resource id of the existing Foundry (AIServices) account the agents call.')
param foundryResourceId string

@description('Foundry project endpoint the agents use.')
param foundryProjectEndpoint string

param foundryModelDeployment string = 'gpt-4.1-mini'

@description('The API + website image; the deploy workflow sets it to the commit being deployed.')
param apiImage string = 'ghcr.io/sebz04/matchmind-api:latest'

@description('Azure SQL region. North Central US stopped accepting new SQL servers, so the database may sit in another allowed region (Canada Central is nearest).')
param sqlLocation string = location

@description('Where budget alerts go.')
param alertEmail string

@description('Monthly budget (USD) with alerts at 50% and 100%: $25 and $50.')
param budgetAmount int = 50

param createBudget bool = true

var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module app 'resources.bicep' = {
  name: 'matchmind-resources'
  scope: rg
  params: {
    location: location
    tags: tags
    principalId: principalId
    sqlLocation: sqlLocation
    foundryProjectEndpoint: foundryProjectEndpoint
    foundryModelDeployment: foundryModelDeployment
    apiImage: apiImage
  }
}

module foundryAccess 'modules/foundry-access.bicep' = {
  name: 'matchmind-foundry-access'
  scope: resourceGroup(split(foundryResourceId, '/')[2], split(foundryResourceId, '/')[4])
  params: {
    accountName: last(split(foundryResourceId, '/'))
    principalId: app.outputs.identityPrincipalId
  }
}

module budget 'modules/budget.bicep' = if (createBudget) {
  name: 'matchmind-budget'
  params: {
    amount: budgetAmount
    alertEmail: alertEmail
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = app.outputs.registryEndpoint
output SERVICE_API_NAME string = app.outputs.appName
output SERVICE_API_URI string = app.outputs.appUri
output MATCHMIND_SQL_URL string = app.outputs.sqlUrl
output MATCHMIND_SQL_SERVER string = app.outputs.sqlServerName
output MATCHMIND_BLOB_ACCOUNT_URL string = app.outputs.blobUrl
output AZURE_IDENTITY_NAME string = app.outputs.identityName
