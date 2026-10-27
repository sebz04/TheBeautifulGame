// Lets the app's identity call the existing Foundry deployment (keyless, like local dev).
param accountName string
param principalId string

var roles = [
  '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Azure AI User
  '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User
]

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: accountName
}

resource grants 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for role in roles: {
    name: guid(account.id, principalId, role)
    scope: account
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]
