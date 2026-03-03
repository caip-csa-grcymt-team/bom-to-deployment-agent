---
title: Provisioner Output Schemas
description: "Output contract for the infra-provisioner agent defining the structure of main.bicep and main.bicepparam"
author: infra-provisioner
ms.date: 2026-03-02
ms.topic: reference
keywords:
  - bicep
  - avm
  - output-schema
  - infrastructure-as-code
---

## Overview

The `infra-provisioner` agent produces exactly two output files. No additional JSON intermediaries are generated.

| File | Purpose |
|---|---|
| `main.bicep` | Complete Bicep template using AVM modules |
| `main.bicepparam` | Parameter file with concrete deployment values |

## main.bicep Structure

### Target Scope

```bicep
targetScope = 'resourceGroup'
```

### Parameters Section

Define all parameters at the top of the file. Follow camelCase naming matching AVM conventions.

Required parameters:

| Parameter | Type | Description |
|---|---|---|
| `applicationName` | `string` | Application identifier (e.g., `min69rg170`) |
| `environment` | `string` | Environment code (`dev`, `stg`, `prd`) |
| `location` | `string` | Azure region (e.g., `westeurope`) |
| `tags` | `object` | Resource tags applied to all resources |
| `vnetAddressPrefix` | `string` | VNet CIDR from `vnet-params.json` |

Resource-specific parameters (conditional on resources in the deployment):

| Parameter Pattern | Type | When Used |
|---|---|---|
| `{resourceType}Count` | `int` | When resource count comes from `resources.json` |
| `{resourceType}SkuName` | `string` | When SKU is configurable |
| `sqlAdminLogin` | `string` | When SQL Server is present |
| `vmAdminUsername` | `string` | When Virtual Machines are present |
| `iacPassword` | `string` (`@secure()`) | When ANY resource requires a password (SQL, VMs, Redis, etc.) |

**Password convention**: Use a single `@secure()` parameter named `iacPassword` for ALL password fields across all resources. Do NOT create separate password parameters per resource. The CI/CD pipeline supplies this value via a GitHub Actions secret (`IAC_PASSWORD`).

```bicep
@secure()
param iacPassword string
```

### Module Ordering

Modules appear in this order within the file:

1. VNet module (always first; all other modules reference its outputs)
2. Private DNS Zone modules (one per required zone)
3. Resource modules (AVM invocations for each resource)

### VNet Module Section

```bicep
// MARK: Virtual Network
module vnet 'br/public:avm/res/network/virtual-network:<version>' = {
  name: 'vnet-deployment'
  params: {
    name: 'vnet-${applicationName}-${environment}-${regionCode}-01'
    location: location
    addressPrefixes: [vnetAddressPrefix]
    subnets: [
      // Subnets from vnet-params.json with names, CIDRs, and delegations
    ]
    tags: tags
  }
}
```

### Private DNS Zone Modules Section

One module per unique DNS zone. Use conditional deployment when the zone applies to an optional resource:

```bicep
// MARK: Private DNS Zones
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

### Resource Modules Section

Each resource uses its AVM module with private access wired:

```bicep
// MARK: Resources
module storageAccount 'br/public:avm/res/storage/storage-account:<version>' = {
  name: 'storage-deployment'
  params: {
    name: storageAccountName
    location: location
    tags: tags
    publicNetworkAccess: 'Disabled'
    privateEndpoints: [
      {
        subnetResourceId: vnet.outputs.subnetResourceIds[peSubnetIndex]
        service: 'blob'
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            { privateDnsZoneResourceId: privateDnsZoneBlob.outputs.resourceId }
          ]
        }
      }
    ]
  }
}
```

### Variables and Helper Expressions

Use `var` declarations for computed names, especially for resources with naming constraints:

```bicep
var regionCode = 'weu' // derived from location
var storageAccountName = take(toLower(replace('st${applicationName}${environment}${regionCode}01', '-', '')), 24)
```

## main.bicepparam Structure

### File Format

```bicep
using './main.bicep'

// Non-secret parameters with concrete values
param applicationName = 'min69rg170'
param environment = 'dev'
param location = 'westeurope'
param tags = {
  authority: 'MIN69'
  project: 'RG170'
  environment: 'dev'
  managedBy: 'bicep'
}
param vnetAddressPrefix = '10.0.0.0/24'

// Resource-specific params
param storageAccountCount = 1

// Password read from environment variable — secret never stored on disk
param iacPassword = readEnvironmentVariable('IAC_PASSWORD')
```

### Rules

- Use `using './main.bicep'` as the first declaration.
- Set all non-secret parameters to concrete values derived from the planner input files.
- For `iacPassword`, use `readEnvironmentVariable('IAC_PASSWORD')` — this reads the value from the
  `IAC_PASSWORD` environment variable at deployment time. Do NOT omit, comment out, or hardcode this parameter.
- Parameter values come from `resources.json` (counts, SKUs), `vnet-params.json` (CIDRs, location), and planner tags (application name, environment).

## Parameter Naming Conventions

- Use camelCase for all parameter names.
- Match AVM module parameter names where applicable (e.g., `skuName`, `tier`, `addressPrefixes`).
- Use descriptive suffixes: `Count`, `SkuName`, `Tier`, `AdminLogin`.
- Use a single `iacPassword` parameter for all password/credential fields — do NOT create per-resource password params.
