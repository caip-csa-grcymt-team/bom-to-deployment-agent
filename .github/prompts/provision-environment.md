---
name: provision-environment
description: Orchestration prompt for infrastructure provisioning workflow
---

# Infrastructure Provisioning Workflow

Automate Azure infrastructure provisioning from an Azure Pricing Calculator BOM export.

## Input Parameters

- **bom_path**: Path to the Azure Pricing Calculator Excel export file
- **authority_id**: Authority/Agency identifier for this project
- **project_id**: Project identifier for resource naming

## Step 1: Parse BOM

Use the `bom-parser` MCP tool to extract resource information from the Excel file.

```
Tool: parse_bom
Input: { "excel_path": "{bom_path}" }
```

Review the parsed resources and identify:

- Azure services to be provisioned
- Regions specified
- SKUs and tiers selected

## Step 2: Plan Network

Apply the `azure-networking` skill to determine network requirements.

Based on the identified resources:

1. **List all services requiring VNet integration**:
   - Services deployed into subnets (AKS, App Service, Container Apps)
   - Services with private endpoints (Storage, Key Vault, databases)
   - Infrastructure services (Firewall, Bastion, Application Gateway)

2. **Determine subnet requirements**:
   - Check minimum sizes from the azure-networking skill reference
   - Identify delegation requirements
   - Group PE-only services together

3. **Calculate VNet size**:
   - Sum all subnet requirements
   - Add 10-20% growth headroom
   - Select appropriate VNet prefix (/22, /23, or /24)

4. **Create network plan output**:

```json
{
  "required_vnet_prefix": 23,
  "subnets": [
    {
      "name": "snet-aks",
      "usage_type": "AKS",
      "prefix_length": 24,
      "reasoning": "AKS minimum requirement"
    }
  ],
  "planning_notes": "..."
}
```

## Step 3: Reserve IPAM

Use the `ipam-client` MCP tool to reserve the VNet address space.

```
Tool: reserve_cidr
Input: {
  "authority_id": "{authority_id}",
  "project_id": "{project_id}",
  "prefix_length": <required_vnet_prefix>
}
```

Store the returned CIDR for subnet allocation.

## Step 4: Allocate Subnets

Calculate specific subnet CIDRs within the reserved VNet address space.

For each planned subnet:

1. Assign a CIDR from the VNet range
2. Ensure no overlaps
3. Maintain proper alignment

Example allocation:

| Subnet | CIDR | Usage |
|--------|------|-------|
| snet-aks | 10.0.0.0/24 | AKS |
| snet-appservice | 10.0.1.0/27 | AppService |
| snet-pe | 10.0.1.32/27 | VM/PrivateEndpoint |

## Step 5: Determine Resource Toggles

Map identified resources to IaC toggle parameters:

| BOM Resource | Toggle Parameter | Value |
|--------------|------------------|-------|
| Azure Kubernetes Service | createAKS | Yes |
| App Service | createAppService | Yes |
| SQL Managed Instance | createSQLMI | Yes |

## Step 6: Update UI Definition

Apply the `ui-definition-patterns` skill to patch `createUiDefinition.json`.

Element patches (use `patches`):

1. **Authority ID**: Set default value to `{authority_id}`
2. **Project ID**: Set default value to `{project_id}`
3. **Resource Toggles**: Set enabled resources to "Yes"

Output parameter patches (use `output_patches`):

4. **vnetAddressPrefix**: Set to reserved CIDR array (e.g., `["10.2.5.64/26"]`)
5. **subnets**: Set to the FULL subnet array from vnet-params.json (ALL subnets, not just one)
6. **useExistingVnet**: Set to `true`

Write the patched UI definition to `output/updated_createUiDefinition.json`.

## Output Files

Generate these files in the `output/` directory:

| File | Content |
|------|---------|
| `resources.json` | List of identified Azure resources from BOM |
| `network-plan.json` | Subnet allocation plan with reasoning |
| `vnet-params.json` | VNet configuration parameters |
| `updated_createUiDefinition.json` | Patched UI definition with defaults |

## Success Criteria

- [ ] All BOM resources identified
- [ ] Network plan includes all required subnets
- [ ] CIDR reservation successful
- [ ] Subnets properly allocated within VNet
- [ ] UI definition patched with all values
- [ ] All output files generated
