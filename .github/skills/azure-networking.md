---
name: azure-networking
description: Azure networking patterns for VNet and subnet sizing
---

# Azure Networking Patterns

Expert knowledge for planning Azure VNet deployments with properly sized subnets based on Azure service requirements and best practices.

## Subnet Requirements Reference

### Compute Services

| Service | Minimum Prefix | Recommended | Usable IPs | Delegation Required |
|---------|---------------|-------------|------------|---------------------|
| **AKS** | /24 | /22 (large clusters) | 251+ | `Microsoft.ContainerService/managedClusters` |
| **Container Apps** | /23 | /23 | 507 | `Microsoft.App/environments` |
| **App Service / Functions** | /28 | /27 | 11-27 | `Microsoft.Web/serverFarms` |
| **VMs / Private Endpoints** | /27-/25 | Based on count | Variable | None |

### Networking Services

| Service | Required Prefix | Usable IPs | Delegation Required | Notes |
|---------|----------------|------------|---------------------|-------|
| **Application Gateway** | /27 | 27 | None | Dedicated subnet required |
| **Azure Firewall** | /26 (exact) | 59 | None | Must be named `AzureFirewallSubnet` |
| **Azure Bastion** | /26 | 59 | None | Must be named `AzureBastionSubnet` |
| **VPN Gateway** | /27 | 27 | None | Must be named `GatewaySubnet` |
| **API Management (stv2)** | /27 | 27 | `Microsoft.ApiManagement/service` | |

### Database Services

| Service | Minimum Prefix | Recommended | Delegation Required |
|---------|---------------|-------------|---------------------|
| **SQL Managed Instance** | /27 | /26 | `Microsoft.Sql/managedInstances` |
| **MySQL Flexible Server** | /28 | /27 | `Microsoft.DBforMySQL/flexibleServers` |
| **PostgreSQL Flexible Server** | /28 | /27 | `Microsoft.DBforPostgreSQL/flexibleServers` |
| **Azure NetApp Files** | /28 | /27 | `Microsoft.NetApp/volumes` |

## Network Planning Strategy

### Step 1: Inventory Resources

Identify all Azure services from the pricing calculator BOM that require VNet integration:

- Services deployed into subnets (AKS, App Service, Container Apps)
- Services with private endpoints (Storage, Key Vault, Cosmos DB, SQL)
- Infrastructure services (Firewall, Bastion, Application Gateway)

### Step 2: Determine Subnet Requirements

For each service:

1. Check if it requires a **dedicated subnet** (Application Gateway, Firewall, Bastion)
2. Check if it requires **subnet delegation** (App Service, AKS, databases)
3. Group services that can share a common **Private Endpoints** subnet

### Step 3: Size Subnets

Apply sizing rules:

- **Minimum**: Azure enforces minimum sizes per service
- **Growth headroom**: Add 10-20% for future scaling
- **Round up**: Use standard CIDR sizes (/24, /25, /26, /27, /28)

### Step 4: Calculate VNet Size

Sum all subnet address spaces and select a VNet prefix that accommodates all subnets with room for future additions:

- Typical small deployment: /24 (256 addresses)
- Typical medium deployment: /23 (512 addresses)
- Typical large deployment: /22 (1024 addresses)

## CIDR Calculation Reference

| Prefix | Addresses | Usable Hosts | Common Use |
|--------|-----------|--------------|------------|
| /16 | 65,536 | 65,531 | Hub VNet |
| /20 | 4,096 | 4,091 | Large spoke |
| /22 | 1,024 | 1,019 | Medium spoke with AKS |
| /23 | 512 | 507 | Container Apps Environment |
| /24 | 256 | 251 | AKS minimum, standard VNet |
| /25 | 128 | 123 | Large VM/PE subnet |
| /26 | 64 | 59 | Firewall, Bastion |
| /27 | 32 | 27 | App Gateway, small services |
| /28 | 16 | 11 | App Service, databases |

## Usage Type Mapping

Use these exact `usage_type` values when creating subnet allocations for the `vnet.module.bicep`:

- `VM/PrivateEndpoint` - VMs and Private Endpoints (no delegation)
- `AppService` - App Service and Functions
- `mySQL` - MySQL Flexible Server
- `Postgres` - PostgreSQL Flexible Server
- `AKS` - Azure Kubernetes Service
- `ContainerApps` - Container Apps Environment
- `ApiManagement` - API Management
- `AppGateway` - Application Gateway
- `Firewall` - Azure Firewall
- `Bastion` - Azure Bastion
- `VpnGateway` - VPN Gateway
- `NetApp` - Azure NetApp Files
- `SQLMI` - SQL Managed Instance

## Example Network Plan

For a deployment with AKS, App Service, SQL MI, and Private Endpoints:

```json
{
  "vnet_prefix": "/22",
  "subnets": [
    {"name": "snet-aks", "prefix": "/24", "usage": "AKS"},
    {"name": "snet-appservice", "prefix": "/27", "usage": "AppService"},
    {"name": "snet-sqlmi", "prefix": "/26", "usage": "SQLMI"},
    {"name": "snet-pe", "prefix": "/26", "usage": "VM/PrivateEndpoint"}
  ]
}
```
