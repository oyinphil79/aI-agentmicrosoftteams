param location string
param tags object
param principalId string

var token = toLower(uniqueString(subscription().id, resourceGroup().id, location))
var tenantId = subscription().tenantId

// Built-in role definition IDs
var roles = {
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908' // Content Safety / Prompt Shields
  azureAIUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Foundry project / Agent Service
  searchIndexDataReader: '1407120a-92aa-4202-b7e9-c0e197c71c8f'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
}

func roleId(id string) string => subscriptionResourceId('Microsoft.Authorization/roleDefinitions', id)

// ---------------------------------------------------------------- identity
// One user-assigned identity is the bot's runtime identity: Azure Bot Service auth, Foundry, Search, Key Vault.
// Each agent additionally gets an Entra Agent ID in the Foundry project (see docs/identity.md).
resource botIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-opscopilot-${token}'
  location: location
  tags: tags
}

// ---------------------------------------------------------------- observability
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${token}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id }
}

// ---------------------------------------------------------------- Microsoft Foundry
resource aiServices 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'ais-${token}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'ais-${token}'
    allowProjectManagement: true
    disableLocalAuth: true // keys disabled: Entra ID only
    publicNetworkAccess: 'Enabled' // Disabled + private endpoints for production
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: aiServices
  name: 'ops-copilot'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: { displayName: 'Ops Copilot', description: 'Multi-agent IT/HR helpdesk' }
}

var models = [
  { name: 'gpt-4.1', model: 'gpt-4.1', version: '2025-04-14', capacity: 50 }
  { name: 'gpt-4.1-mini', model: 'gpt-4.1-mini', version: '2025-04-14', capacity: 50 }
  { name: 'text-embedding-3-large', model: 'text-embedding-3-large', version: '1', capacity: 50 }
]

@batchSize(1)
resource deployments 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [for m in models: {
  parent: aiServices
  name: m.name
  sku: { name: 'GlobalStandard', capacity: m.capacity }
  properties: {
    model: { format: 'OpenAI', name: m.model, version: m.version }
    raiPolicyName: 'Microsoft.DefaultV2' // default content filters incl. jailbreak detection
  }
}]

// ---------------------------------------------------------------- Azure AI Search (Foundry IQ knowledge source)
resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: 'srch-${token}'
  location: location
  tags: tags
  sku: { name: 'basic' }
  identity: { type: 'SystemAssigned' }
  properties: {
    disableLocalAuth: true
    semanticSearch: 'free'
    publicNetworkAccess: 'enabled'
  }
}

// ---------------------------------------------------------------- Key Vault (certificates only - no app keys needed)
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${token}'
  location: location
  tags: tags
  properties: {
    tenantId: tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    enablePurgeProtection: true
  }
}

// ---------------------------------------------------------------- hosting
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${token}'
  location: location
  tags: tags
  sku: { name: 'B1' }
  kind: 'linux'
  properties: { reserved: true }
}

resource web 'Microsoft.Web/sites@2024-04-01' = {
  name: 'app-opscopilot-${token}'
  location: location
  tags: union(tags, { 'azd-service-name': 'bot' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${botIdentity.id}': {} } }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    keyVaultReferenceIdentity: botIdentity.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'python -m ops_copilot.bot.app'
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        { name: 'OPS_COPILOT_MODE', value: 'azure' }
        { name: 'PYTHONPATH', value: '/home/site/wwwroot/src' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'AZURE_CLIENT_ID', value: botIdentity.properties.clientId } // DefaultAzureCredential -> this MI
        { name: 'AZURE_OPENAI_ENDPOINT', value: 'https://${aiServices.properties.customSubDomainName}.openai.azure.com/' }
        { name: 'AZURE_AI_PROJECT_ENDPOINT', value: 'https://${aiServices.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}' }
        { name: 'AZURE_CONTENT_SAFETY_ENDPOINT', value: aiServices.properties.endpoint }
        { name: 'AZURE_SEARCH_ENDPOINT', value: 'https://${search.name}.search.windows.net' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__AUTHTYPE', value: 'UserManagedIdentity' }
        { name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID', value: botIdentity.properties.clientId }
        { name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID', value: tenantId }
      ]
    }
  }
}

// ---------------------------------------------------------------- Azure Bot Service (Teams + Outlook channels)
resource bot 'Microsoft.BotService/botServices@2022-09-15' = {
  name: 'bot-opscopilot-${token}'
  location: 'global'
  tags: tags
  kind: 'azurebot'
  sku: { name: 'F0' }
  properties: {
    displayName: 'Ops Copilot'
    endpoint: 'https://${web.properties.defaultHostName}/api/messages'
    msaAppType: 'UserAssignedMSI'
    msaAppId: botIdentity.properties.clientId
    msaAppTenantId: tenantId
    msaAppMSIResourceId: botIdentity.id
  }
}

resource teamsChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = {
  parent: bot
  name: 'MsTeamsChannel'
  location: 'global'
  properties: { channelName: 'MsTeamsChannel', properties: { isEnabled: true } }
}

resource outlookChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = {
  parent: bot
  name: 'OutlookChannel'
  location: 'global'
  properties: { channelName: 'OutlookChannel' }
}

// ---------------------------------------------------------------- RBAC (least privilege)
resource botOpenAI 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, botIdentity.id, roles.cognitiveServicesOpenAIUser)
  scope: aiServices
  properties: { principalId: botIdentity.properties.principalId, principalType: 'ServicePrincipal', roleDefinitionId: roleId(roles.cognitiveServicesOpenAIUser) }
}

resource botContentSafety 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, botIdentity.id, roles.cognitiveServicesUser)
  scope: aiServices
  properties: { principalId: botIdentity.properties.principalId, principalType: 'ServicePrincipal', roleDefinitionId: roleId(roles.cognitiveServicesUser) }
}

resource botFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(project.id, botIdentity.id, roles.azureAIUser)
  scope: project
  properties: { principalId: botIdentity.properties.principalId, principalType: 'ServicePrincipal', roleDefinitionId: roleId(roles.azureAIUser) }
}

resource botSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, botIdentity.id, roles.searchIndexDataReader)
  scope: search
  properties: { principalId: botIdentity.properties.principalId, principalType: 'ServicePrincipal', roleDefinitionId: roleId(roles.searchIndexDataReader) }
}

resource botVault 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, botIdentity.id, roles.keyVaultSecretsUser)
  scope: vault
  properties: { principalId: botIdentity.properties.principalId, principalType: 'ServicePrincipal', roleDefinitionId: roleId(roles.keyVaultSecretsUser) }
}

// Search's own identity calls the embedding model (integrated vectorizer) - no keys.
resource searchOpenAI 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, search.id, roles.cognitiveServicesOpenAIUser)
  scope: aiServices
  properties: { principalId: search.identity.principalId, principalType: 'ServicePrincipal', roleDefinitionId: roleId(roles.cognitiveServicesOpenAIUser) }
}

// Developer access for local runs, evals and index setup.
var devAiRoles = empty(principalId) ? [] : [roles.cognitiveServicesOpenAIUser, roles.cognitiveServicesUser]
var devSearchRoles = empty(principalId) ? [] : [roles.searchIndexDataContributor, roles.searchServiceContributor]

resource devAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for r in devAiRoles: {
  name: guid(aiServices.id, principalId, r)
  scope: aiServices
  properties: { principalId: principalId, principalType: 'User', roleDefinitionId: roleId(r) }
}]

resource devSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for r in devSearchRoles: {
  name: guid(search.id, principalId, r)
  scope: search
  properties: { principalId: principalId, principalType: 'User', roleDefinitionId: roleId(r) }
}]

resource devProject 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(project.id, principalId, roles.azureAIUser)
  scope: project
  properties: { principalId: principalId, principalType: 'User', roleDefinitionId: roleId(roles.azureAIUser) }
}

output openAiEndpoint string = 'https://${aiServices.properties.customSubDomainName}.openai.azure.com/'
output projectEndpoint string = 'https://${aiServices.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
output aiServicesEndpoint string = aiServices.properties.endpoint
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output botIdentityClientId string = botIdentity.properties.clientId
output botEndpoint string = 'https://${web.properties.defaultHostName}/api/messages'
