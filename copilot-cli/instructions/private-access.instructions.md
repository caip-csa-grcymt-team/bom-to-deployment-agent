---
description: "Private endpoint, VNet integration, and Private DNS Zone patterns for the infra-provisioner agent"
applyTo: "copilot-cli/**"
---

## Scope

This instruction file defines the two private connectivity patterns used by the `infra-provisioner` agent. Every resource in the generated `main.bicep` must use one of these patterns. Public network access is disabled on all resources.

## Critical Rules

1. Set `publicNetworkAccess: 'Disabled'` on every resource that supports it.
2. Every Private DNS Zone must be linked to the VNet via `virtualNetworkLinks`.
3. All Private Endpoints connect to a dedicated PE subnet.
4. VNet-integrated services get their own delegated subnets.
5. DNS zone names are Azure-standard strings. Never customize them.

## Pattern A: Private Endpoint

Use this pattern for most Azure services. The AVM module's built-in `privateEndpoints` parameter handles PE creation, DNS zone group registration, and subnet binding in a single declaration.

### AVM Parameter Pattern

```bicep
module storageAccount 'br/public:avm/res/storage/storage-account:<version>' = {
  name: 'storageAccount-deployment'
  params: {
    name: storageAccountName
    location: location
    tags: tags
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
    }
    privateEndpoints: [
      {
        subnetResourceId: vnet.outputs.subnetResourceIds[0] // PE subnet
        service: 'blob'
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            {
              privateDnsZoneResourceId: privateDnsZoneBlob.outputs.resourceId
            }
          ]
        }
      }
    ]
  }
}
```

### Pattern A Resource Reference Table

| Azure Service | ARM Type | Group ID | Private DNS Zone |
|---|---|---|---|
| Storage (blob) | `Microsoft.Storage/storageAccounts` | `blob` | `privatelink.blob.core.windows.net` |
| Storage (file) | `Microsoft.Storage/storageAccounts` | `file` | `privatelink.file.core.windows.net` |
| Storage (table) | `Microsoft.Storage/storageAccounts` | `table` | `privatelink.table.core.windows.net` |
| Storage (queue) | `Microsoft.Storage/storageAccounts` | `queue` | `privatelink.queue.core.windows.net` |
| Storage (dfs) | `Microsoft.Storage/storageAccounts` | `dfs` | `privatelink.dfs.core.windows.net` |
| Key Vault | `Microsoft.KeyVault/vaults` | `vault` | `privatelink.vaultcore.azure.net` |
| SQL Server | `Microsoft.Sql/servers` | `sqlServer` | `privatelink.database.windows.net` |
| Cosmos DB (NoSQL) | `Microsoft.DocumentDB/databaseAccounts` | `Sql` | `privatelink.documents.azure.com` |
| Cosmos DB (MongoDB) | `Microsoft.DocumentDB/databaseAccounts` | `MongoDB` | `privatelink.mongo.cosmos.azure.com` |
| Cosmos DB (Cassandra) | `Microsoft.DocumentDB/databaseAccounts` | `Cassandra` | `privatelink.cassandra.cosmos.azure.com` |
| Cosmos DB (Gremlin) | `Microsoft.DocumentDB/databaseAccounts` | `Gremlin` | `privatelink.gremlin.cosmos.azure.com` |
| Cosmos DB (Table) | `Microsoft.DocumentDB/databaseAccounts` | `Table` | `privatelink.table.cosmos.azure.com` |
| ACR | `Microsoft.ContainerRegistry/registries` | `registry` | `privatelink.azurecr.io` |
| Redis Cache | `Microsoft.Cache/redis` | `redisCache` | `privatelink.redis.cache.windows.net` |
| Managed Redis | `Microsoft.Cache/redisEnterprise` | `redisEnterprise` | `privatelink.redis.azure.net` |
| Event Hub | `Microsoft.EventHub/namespaces` | `namespace` | `privatelink.servicebus.windows.net` |
| Service Bus | `Microsoft.ServiceBus/namespaces` | `namespace` | `privatelink.servicebus.windows.net` |
| Cognitive Services | `Microsoft.CognitiveServices/accounts` | `account` | `privatelink.cognitiveservices.azure.com` |
| Azure OpenAI | `Microsoft.CognitiveServices/accounts` | `account` | `privatelink.openai.azure.com` |
| AI Foundry | `Microsoft.CognitiveServices/accounts` | `account` | `privatelink.services.ai.azure.com` |
| AI Search | `Microsoft.Search/searchServices` | `searchService` | `privatelink.search.windows.net` |
| App Service / Functions | `Microsoft.Web/sites` | `sites` | `privatelink.azurewebsites.net` |
| API Management | `Microsoft.ApiManagement/service` | `Gateway` | `privatelink.azure-api.net` |
| AKS (API Server) | `Microsoft.ContainerService/managedClusters` | `management` | `privatelink.{region}.azmk8s.io` |
| Static Web App | `Microsoft.Web/staticSites` | `staticSites` | `privatelink.azurestaticapps.net` |
| Web PubSub | `Microsoft.SignalRService/webPubSub` | `webpubsub` | `privatelink.webpubsub.azure.com` |
| App Configuration | `Microsoft.AppConfiguration/configurationStores` | `configurationStores` | `privatelink.azconfig.io` |

### Multi-Zone DNS Group (Cognitive Services / OpenAI / AI Foundry)

When deploying Azure OpenAI or AI Foundry accounts, configure multiple DNS zones on the same private endpoint:

```bicep
privateEndpoints: [
  {
    subnetResourceId: peSubnetId
    service: 'account'
    privateDnsZoneGroup: {
      privateDnsZoneGroupConfigs: [
        {
          privateDnsZoneResourceId: privateDnsZoneCognitiveServices.outputs.resourceId
        }
        {
          privateDnsZoneResourceId: privateDnsZoneOpenAI.outputs.resourceId
        }
        {
          privateDnsZoneResourceId: privateDnsZoneAIFoundry.outputs.resourceId
        }
      ]
    }
  }
]
```

### Storage Account Multi-Service Private Endpoints

Storage accounts may require up to five private endpoints (one per sub-service). Create each with its own DNS zone:

```bicep
privateEndpoints: [
  {
    subnetResourceId: peSubnetId
    service: 'blob'
    privateDnsZoneGroup: {
      privateDnsZoneGroupConfigs: [
        { privateDnsZoneResourceId: privateDnsZoneBlob.outputs.resourceId }
      ]
    }
  }
  {
    subnetResourceId: peSubnetId
    service: 'file'
    privateDnsZoneGroup: {
      privateDnsZoneGroupConfigs: [
        { privateDnsZoneResourceId: privateDnsZoneFile.outputs.resourceId }
      ]
    }
  }
  // Add table, queue, dfs as needed
]
```

## Pattern B: VNet Integration

Use this pattern for services that require delegated subnet connectivity instead of Private Endpoints. These services inject directly into a VNet subnet.

### Pattern B Resource Reference Table

| Azure Service | ARM Type | Delegation | Private DNS Zone |
|---|---|---|---|
| MySQL Flexible Server | `Microsoft.DBforMySQL/flexibleServers` | `Microsoft.DBforMySQL/flexibleServers` | `private.mysql.database.azure.com` |
| PostgreSQL Flexible Server | `Microsoft.DBforPostgreSQL/flexibleServers` | `Microsoft.DBforPostgreSQL/flexibleServers` | `private.postgres.database.azure.com` |
| Container App Environment | `Microsoft.App/managedEnvironments` | `Microsoft.App/environments` | `privatelink.{region}.azurecontainerapps.io` |

Note: VNet-integrated services use `private.*` zones (no `privatelink` prefix) for MySQL and PostgreSQL.

### AVM Parameter Pattern for VNet-Integrated Services

MySQL Flexible Server:

```bicep
module mysqlServer 'br/public:avm/res/db-for-my-sql/flexible-server:<version>' = {
  name: 'mysql-deployment'
  params: {
    name: mysqlServerName
    location: location
    tags: tags
    skuName: 'Standard_B1ms'
    tier: 'Burstable'
    delegatedSubnetResourceId: vnet.outputs.subnetResourceIds[mysqlSubnetIndex]
    privateDnsZoneResourceId: privateDnsZoneMysql.outputs.resourceId
  }
}
```

PostgreSQL Flexible Server:

```bicep
module postgresServer 'br/public:avm/res/db-for-postgre-sql/flexible-server:<version>' = {
  name: 'postgres-deployment'
  params: {
    name: postgresServerName
    location: location
    tags: tags
    skuName: 'Standard_B1ms'
    tier: 'Burstable'
    delegatedSubnetResourceId: vnet.outputs.subnetResourceIds[psqlSubnetIndex]
    privateDnsZoneResourceId: privateDnsZonePostgres.outputs.resourceId
  }
}
```

Container App Environment:

```bicep
module containerAppEnv 'br/public:avm/res/app/managed-environment:<version>' = {
  name: 'cae-deployment'
  params: {
    name: caeName
    location: location
    tags: tags
    logAnalyticsWorkspaceResourceId: logAnalytics.outputs.resourceId
    infrastructureSubnetId: vnet.outputs.subnetResourceIds[caeSubnetIndex]
  }
}
```

## DNS Zone Module Pattern

Create each Private DNS Zone using the AVM module and link it to the VNet:

```bicep
module privateDnsZoneBlob 'br/public:avm/res/network/private-dns-zone:<version>' = {
  name: 'pdnsz-blob-deployment'
  params: {
    name: 'privatelink.blob.core.windows.net'
    tags: tags
    virtualNetworkLinks: [
      {
        virtualNetworkResourceId: vnet.outputs.resourceId
        registrationEnabled: false
      }
    ]
  }
}
```

Every DNS zone follows this same pattern. Produce one module invocation per unique zone required by the deployment.

## Subnet Strategy

### Private Endpoint Subnet

A single dedicated subnet hosts all Private Endpoints across all services. Size it based on expected PE count (each PE consumes one IP):

- Minimum: `/28` (11 usable IPs) for small deployments
- Recommended: `/26` (59 usable IPs) for medium deployments
- Large: `/24` (251 usable IPs) for deployments with many resources

### VNet-Integrated Subnets

Each VNet-integrated service requires its own dedicated delegated subnet:

| Service | Minimum Subnet Size | Delegation |
|---|---|---|
| MySQL Flexible Server | `/28` (11 IPs) | `Microsoft.DBforMySQL/flexibleServers` |
| PostgreSQL Flexible Server | `/28` (11 IPs) | `Microsoft.DBforPostgreSQL/flexibleServers` |
| Container App Environment | `/23` (507 IPs) | `Microsoft.App/environments` |
| App Service (outbound) | `/28` (11 IPs) | `Microsoft.Web/serverFarms` |
| AKS | `/24` (251 IPs) minimum | None (but dedicated) |
| Application Gateway | `/27` (27 IPs) | None |
| Azure Bastion | `/26` (59 IPs) | None |
| Azure Firewall | `/26` (59 IPs) | `Microsoft.Network/azureFirewalls` |

## publicNetworkAccess Configuration Reference

| Service | Property Path | Value |
|---|---|---|
| Storage Account | `publicNetworkAccess` | `'Disabled'` |
| Key Vault | `publicNetworkAccess` | `'Disabled'` |
| SQL Server | `publicNetworkAccess` | `'Disabled'` |
| Cosmos DB | `publicNetworkAccess` | `'Disabled'` |
| ACR | `publicNetworkAccess` | `'Disabled'` |
| AI Search | `publicNetworkAccess` | `'disabled'` |
| Cognitive Services / OpenAI | `publicNetworkAccess` | `'Disabled'` |
| Event Hub | `publicNetworkAccess` | `'Disabled'` |
| Redis Cache | `publicNetworkAccess` | `'Disabled'` |
| API Management | `publicNetworkAccess` | `'Disabled'` |
| App Service | `publicNetworkAccess` | `'Disabled'` |
| MySQL Flexible | `network.publicNetworkAccess` | `'Disabled'` |
| PostgreSQL Flexible | `network.publicNetworkAccess` | `'Disabled'` |
| Log Analytics | `publicNetworkAccessForIngestion` + `publicNetworkAccessForQuery` | `'Disabled'` |
| Application Insights | `publicNetworkAccessForIngestion` + `publicNetworkAccessForQuery` | `'Disabled'` |

Note: AVM modules handle the `publicNetworkAccess` property internally when `privateEndpoints` are configured. Explicitly set it when the AVM module exposes it as a parameter.

## Full DNS Zone Inventory

All Private DNS Zones that may be needed. Only create zones for resources present in the deployment.

| Zone Name | Services |
|---|---|
| `privatelink.blob.core.windows.net` | Storage (blob) |
| `privatelink.file.core.windows.net` | Storage (file) |
| `privatelink.table.core.windows.net` | Storage (table) |
| `privatelink.queue.core.windows.net` | Storage (queue) |
| `privatelink.dfs.core.windows.net` | Storage (Data Lake) |
| `privatelink.web.core.windows.net` | Storage (static website) |
| `privatelink.database.windows.net` | Azure SQL |
| `privatelink.documents.azure.com` | Cosmos DB (NoSQL) |
| `privatelink.mongo.cosmos.azure.com` | Cosmos DB (MongoDB) |
| `privatelink.cassandra.cosmos.azure.com` | Cosmos DB (Cassandra) |
| `privatelink.gremlin.cosmos.azure.com` | Cosmos DB (Gremlin) |
| `privatelink.table.cosmos.azure.com` | Cosmos DB (Table) |
| `privatelink.vaultcore.azure.net` | Key Vault |
| `privatelink.azurecr.io` | Container Registry |
| `privatelink.azurewebsites.net` | App Service, Functions |
| `privatelink.search.windows.net` | AI Search |
| `privatelink.cognitiveservices.azure.com` | Cognitive Services |
| `privatelink.openai.azure.com` | Azure OpenAI |
| `privatelink.services.ai.azure.com` | AI Foundry |
| `privatelink.servicebus.windows.net` | Event Hubs, Service Bus |
| `privatelink.redis.cache.windows.net` | Redis Cache |
| `privatelink.redis.azure.net` | Azure Managed Redis |
| `privatelink.azure-api.net` | API Management |
| `privatelink.monitor.azure.com` | Azure Monitor (AMPLS) |
| `privatelink.oms.opinsights.azure.com` | Log Analytics (AMPLS) |
| `privatelink.ods.opinsights.azure.com` | Log Analytics ODS (AMPLS) |
| `privatelink.agentsvc.azure-automation.net` | Automation Agent (AMPLS) |
| `privatelink.azurestaticapps.net` | Static Web Apps |
| `privatelink.webpubsub.azure.com` | Web PubSub |
| `privatelink.azconfig.io` | App Configuration |
| `private.mysql.database.azure.com` | MySQL Flexible (VNet integration) |
| `private.postgres.database.azure.com` | PostgreSQL Flexible (VNet integration) |
| `privatelink.{region}.azurecontainerapps.io` | Container Apps Environment |
| `privatelink.{region}.azmk8s.io` | AKS API Server |
| `privatelink.mysql.database.azure.com` | MySQL Flexible (PE approach) |
| `privatelink.postgres.database.azure.com` | PostgreSQL Flexible (PE approach) |
