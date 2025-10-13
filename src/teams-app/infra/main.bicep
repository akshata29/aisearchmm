param location string = resourceGroup().location
param appName string
param botAppId string
@secure()
param botAppPassword string
param ragApiBaseUrl string
param allowedOrigins array = [
  'https://teams.microsoft.com',
  'https://*.teams.microsoft.com'
]
param appServicePlanSku string = 'P1v3'

var hostingPlanName = '${appName}-plan'
var siteName = appName
var botName = '${appName}-bot'

resource hostingPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: hostingPlanName
  location: location
  sku: {
    name: appServicePlanSku
    tier: 'PremiumV3'
  }
  kind: 'app'
  properties: {
    reserved: true
  }
}

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: siteName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: hostingPlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'NODE|18-lts'
      appSettings: [
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '0'
        }
        {
          name: 'PORT'
          value: '3978'
        }
        {
          name: 'MicrosoftAppId'
          value: botAppId
        }
        {
          name: 'MicrosoftAppPassword'
          value: botAppPassword
        }
        {
          name: 'RAG_API_BASE_URL'
          value: ragApiBaseUrl
        }
        {
          name: 'ALLOWED_ORIGINS'
          value: join(union(allowedOrigins, [format('https://{0}.azurewebsites.net', siteName)]), ',')
        }
      ]
    }
  }
}

resource botService 'Microsoft.BotService/botServices@2022-09-15' = {
  name: botName
  location: location
  sku: {
    name: 'F0'
    tier: 'F0'
  }
  kind: 'azurebot'
  properties: {
    displayName: appName
    description: 'Teams AI bot for multimodal RAG integration'
    iconUrl: 'https://docs.microsoft.com/en-us/azure/bot-service/media/overview/architecture-resize.png'
    endpoint: format('https://{0}.azurewebsites.net/api/messages', siteName)
    msaAppId: botAppId
    developerAppInsightsApplicationId: ''
    developerAppInsightsKey: ''
    isCmekEnabled: false
  }
  dependsOn: [
    webApp
  ]
}

output webAppUrl string = format('https://{0}.azurewebsites.net', siteName)
output botEndpoint string = format('https://{0}/api/messages', webApp.properties.defaultHostName)
