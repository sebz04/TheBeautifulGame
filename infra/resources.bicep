// The app and its data. Everything the API touches is reached with one user-assigned
// managed identity (no keys, no passwords): image pull, Azure SQL, Blob, and Foundry.
param location string
param tags object
param principalId string
param foundryProjectEndpoint string
param foundryModelDeployment string

var token = toLower(uniqueString(subscription().id, resourceGroup().id, location))
var appName = 'ca-matchmind-api'
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  blobReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  blobContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-matchmind-${token}'
  location: location
  tags: tags
}

// Monitoring: traces from the agents and the API land in Application Insights.
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-matchmind-${token}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-matchmind-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id }
}

// Images, built in the registry by `azd deploy` (remote build).
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crmatchmind${token}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, roles.acrPull)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Tracking frames (Parquet), read by the API; the deployer uploads them (seed_cloud.py).
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stmatchmind${take(token, 11)}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource tracking 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs
  name: 'tracking'
}

resource appReadsBlobs 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, roles.blobReader)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobReader)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource deployerWritesBlobs 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, principalId, roles.blobContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobContributor)
    principalId: principalId
    principalType: 'User'
  }
}

// Azure SQL: Entra ID sign-in only; the deployer is the admin and grants the app's identity
// read/write (scripts/seed_cloud.py). Basic tier: always on (no cold start), about $5/month.
resource sql 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: 'sql-matchmind-${token}'
  location: location
  tags: tags
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      azureADOnlyAuthentication: true
      login: 'matchmind-admin'
      principalType: 'User'
      sid: principalId
      tenantId: subscription().tenantId
    }
  }
}

resource allowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sql
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource db 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sql
  name: 'matchmind'
  location: location
  tags: tags
  sku: { name: 'Basic', tier: 'Basic', capacity: 5 }
  properties: { maxSizeBytes: 2147483648 }
}

// The API + website: one replica (the live-run rate limits are per replica), always on.
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-matchmind-${token}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

var host = '${appName}.${env.properties.defaultDomain}'
var sqlUrl = 'mssql+pyodbc://@${sql.properties.fullyQualifiedDomainName}/${db.name}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no'

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
      secrets: [{ name: 'appinsights', value: insights.properties.ConnectionString }]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'MATCHMIND_DB_URL', value: sqlUrl }
            { name: 'MATCHMIND_BLOB_ACCOUNT_URL', value: storage.properties.primaryEndpoints.blob }
            { name: 'MATCHMIND_APPINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights' }
            { name: 'MATCHMIND_API_HOST', value: host }
            { name: 'MATCHMIND_WEB_ORIGIN', value: 'https://${host}' }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'FOUNDRY_MODEL_DEPLOYMENT', value: foundryModelDeployment }
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [pull]
}

output appName string = app.name
output appUri string = 'https://${host}'
output registryEndpoint string = registry.properties.loginServer
output sqlUrl string = sqlUrl
output sqlServerName string = sql.name
output blobUrl string = storage.properties.primaryEndpoints.blob
output identityName string = identity.name
output identityPrincipalId string = identity.properties.principalId
