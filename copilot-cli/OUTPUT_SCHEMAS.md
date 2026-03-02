# Output File Schemas for Infrastructure Planning

This document defines the exact JSON schemas that Copilot CLI must use when generating output files.

## Inter-Agent Contract

The three JSON files below are produced by the `infra-planner` agent and consumed by the `infra-provisioner` agent. The provisioner uses these to generate `main.bicep` and `main.bicepparam`.

## resources.json

```json
{
  "resources": [
    {
      "type": "string — Azure ARM resource type (e.g., Microsoft.Compute/virtualMachines, Microsoft.Storage/storageAccounts, Microsoft.Sql/servers/databases)",
      "name": "string",
      "sku": "string",
      "count": "number",
      "properties": {}
    }
  ],
  "summary": {
    "totalResources": "number",
    "requiresVnet": "boolean"
  }
}
```

## network-plan.json

```json
{
  "vnetSize": "string (e.g., /27)",
  "subnets": [
    {
      "name": "string",
      "size": "string (e.g., /28)",
      "purpose": "string",
      "services": ["string"]
    }
  ],
  "totalIpsRequired": "number",
  "reasoning": "string"
}
```

## vnet-params.json (CRITICAL)

This is the primary output used for VNet deployment. Field names must match exactly.

```json
{
  "vnetName": "string (format: {authority}-{project}-Vnet, e.g., MIN69-RG170-Vnet)",
  "vnetAddressPrefix": "string (CIDR from IPAM, e.g., 10.2.5.64/27)",
  "location": "westeurope",
  "subnets": [
    {
      "addressPrefix": "string (subnet CIDR within vnet)",
      "usage": "string (one of: VM/PrivateEndpoint, AppService, mySQL, Postgres, AKS, ContainerApps, ApiManagement, AppGateway, Firewall, Bastion, VpnGateway, NetApp, SQLMI)"
    }
  ],
  "ipamReservation": {
    "id": "string (from reserve_cidr response)",
    "cidr": "string (from reserve_cidr response)"
  },
  "tags": {
    "authority": "string",
    "project": "string"
  }
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `vnetName` | string | VNet resource name (format: `{authority}-{project}-Vnet`, e.g., `MIN69-RG170-Vnet`) |
| `vnetAddressPrefix` | string | Full VNet CIDR from IPAM reservation |
| `location` | string | Azure region (default: `westeurope`) |
| `subnets` | array | List of subnet definitions |
| `ipamReservation.id` | string | IPAM reservation ID from `reserve_cidr` tool |
| `ipamReservation.cidr` | string | CIDR block from `reserve_cidr` tool |

### Subnet Object

| Field | Type | Description |
|-------|------|-------------|
| `addressPrefix` | string | Subnet CIDR within the VNet address space |
| `usage` | string | Subnet purpose: `VM/PrivateEndpoint`, `AppService`, `mySQL`, `Postgres`, `AKS`, `ContainerApps`, `ApiManagement`, `AppGateway`, `Firewall`, `Bastion`, `VpnGateway`, `NetApp`, `SQLMI` |
