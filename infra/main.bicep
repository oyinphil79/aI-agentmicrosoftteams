// Ops Copilot - Azure infrastructure (keyless: Managed Identity + Entra RBAC everywhere).
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('azd environment name, used to name resources')
param environmentName string

@description('Primary region (must offer the model deployments below)')
param location string

@description('Object ID of the developer running azd, granted data-plane roles for local dev')
param principalId string = ''

var tags = { 'azd-env-name': environmentName, app: 'ops-copilot' }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    tags: tags
    principalId: principalId
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_OPENAI_ENDPOINT string = resources.outputs.openAiEndpoint
output AZURE_AI_PROJECT_ENDPOINT string = resources.outputs.projectEndpoint
output AZURE_CONTENT_SAFETY_ENDPOINT string = resources.outputs.aiServicesEndpoint
output AZURE_SEARCH_ENDPOINT string = resources.outputs.searchEndpoint
output BOT_IDENTITY_CLIENT_ID string = resources.outputs.botIdentityClientId
output BOT_ENDPOINT string = resources.outputs.botEndpoint
