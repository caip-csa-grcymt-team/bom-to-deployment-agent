---
name: ui-definition-patterns
description: Azure Portal UI definition structure and patching rules for createUiDefinition.json
---

# Azure UI Definition Patterns

Expert knowledge for patching Azure Portal UI definitions (`createUiDefinition.json`) with computed default values based on infrastructure planning outputs.

## createUiDefinition.json Structure

### Top-Level Schema

```json
{
  "$schema": "https://schema.management.azure.com/...",
  "handler": "Microsoft.Azure.CreateUIDef",
  "version": "0.1.2-preview",
  "parameters": {
    "config": { ... },
    "basics": [ ... ],
    "steps": [ ... ],
    "outputs": { ... }
  }
}
```

### Parameters Section

- **basics**: First wizard step, always visible, contains subscription/resource group selectors
- **steps**: Array of additional wizard steps with custom elements
- **outputs**: Maps UI element values to ARM template parameters

### Element Structure

Every UI element has:

```json
{
  "name": "elementName",
  "type": "Microsoft.Common.TextBox",
  "label": "Display Label",
  "toolTip": "Help text",
  "defaultValue": "",
  "constraints": { ... },
  "visible": true
}
```

## Common Element Types

| Type | Purpose | defaultValue Type |
|------|---------|-------------------|
| `Microsoft.Common.TextBox` | Text input | `string` |
| `Microsoft.Common.DropDown` | Single selection | `string` (selected value) |
| `Microsoft.Common.CheckBox` | Boolean toggle | `boolean` |
| `Microsoft.Common.OptionsGroup` | Radio buttons | `string` (selected value) |
| `Microsoft.Solutions.ArmApiControl` | Hidden API calls | N/A |
| `Microsoft.Common.EditableGrid` | Tabular data | `array` of objects |

## Patching Rules

### Authority/Agency ID

- **Find by**: Look for TextBox with label containing "authority", "agency", or "agency ID"
- **Location**: Usually in `basics` step
- **Default format**: String like `"MIN01"`

### Project ID

- **Find by**: Look for TextBox with label containing "project", "project ID", or "project identifier"
- **Location**: Usually in `basics` step
- **Default format**: String like `"RG100"`

### VNet CIDR / Address Prefix

- **Find by**: Look for TextBox in networking step with label containing "address", "CIDR", "prefix", or "VNet"
- **Location**: Usually in a step named "networking" or "network"
- **Default format**: CIDR notation string like `"10.0.0.0/24"`

### Subnet Grid/Table

- **Find by**: Look for EditableGrid with columns for name, address prefix, and usage
- **Location**: Usually in networking step
- **Default format**: Array of subnet objects

```json
[
  {
    "name": "snet-aks",
    "addressPrefix": "10.0.0.0/24",
    "usage": "AKS"
  },
  {
    "name": "snet-pe",
    "addressPrefix": "10.0.1.0/26",
    "usage": "VM/PrivateEndpoint"
  }
]
```

### Output Parameters (Literal Values)

Some parameters in the `outputs.parameters` section are literal values, not bound to any UI element. These **must** be patched using `output_patches` instead of `patches`.

| Parameter | Type | Description |
|-----------|------|-------------|
| `vnetAddressPrefix` | array | VNet CIDR array (e.g., `["10.2.5.64/26"]`) |
| `subnets` | array | Full subnet allocation array from vnet-params.json |
| `useExistingVnet` | boolean | Always `true` (VNet pre-created by pipeline) |

**Critical**: The `subnets` output parameter must contain ALL subnets from `vnet-params.json` — not just one. This ensures the Bicep deployment receives the full network topology.

Example `output_patches`:

```json
[
  {"parameter_name": "vnetAddressPrefix", "value": ["10.2.5.64/26"]},
  {"parameter_name": "subnets", "value": [
    {"addressPrefix": "10.2.5.64/27", "usage": "AppGateway"},
    {"addressPrefix": "10.2.5.96/27", "usage": "VM/PrivateEndpoint"}
  ]},
  {"parameter_name": "useExistingVnet", "value": true}
]
```

### VM Batches Configuration

> **Note**: VM batch configuration uses a **Hybrid Repeatable Sections** pattern instead of EditableGrid. This enables pre-populated default values from BOM analysis.

#### Control Architecture

1. **vmBatchCount Slider** (0-5): Controls how many batch sections are visible
2. **batch{N}Section** (1-5): Individual sections containing all VM configuration fields

#### Finding Elements to Patch

| Element | Location | Path Pattern |
|---------|----------|--------------|
| Batch Count | Compute step | `steps[compute].vmBatchCount` |
| Batch N Config | Compute step | `steps[compute].batch{N}Section.batch{N}{Field}` |

#### Field Naming Convention

Each batch section (1-5) contains these fields:

**IMPORTANT**: For DropDown defaultValue patching, use the LABEL format (see mapping tables in infra-planner agent).

| Field | Element Name Pattern | Type | Default |
|-------|---------------------|------|---------|
| Batch Name | `batch{N}Name` | TextBox | A, B, C, D, E |
| VM Count | `batch{N}Count` | DropDown | "2" |
| VM Size | `batch{N}Size` | DropDown | Use LABEL: "Standard_D4s_v6 (4 vCPU, 16 GB)" |
| Subnet Index | `batch{N}Subnet` | DropDown | "0" |
| OS Image | `batch{N}Image` | DropDown | Use LABEL: "Ubuntu 24.04 LTS" |
| Disk Size | `batch{N}DiskSize` | DropDown | "128" |
| Disk Type | `batch{N}DiskType` | DropDown | Use LABEL: "Standard SSD LRS" |
| Disk Delete | `batch{N}DiskDelete` | DropDown | "Delete" |

#### VM Image Presets

The `vmImagePreset` field uses preset IDs that expand to full image details (publisher, offer, SKU, OS type). 

**CRITICAL**: For `defaultValue` patching, use the **LABEL** (Description column), not the Preset ID.

| Preset ID (OUTPUT value) | Description (use for defaultValue) | OS Type |
|--------------------------|-----------------------------------|---------|
| `ubuntu-24-lts` | Ubuntu 24.04 LTS | Linux |
| `ubuntu-22-lts` | Ubuntu 22.04 LTS | Linux |
| `windows-2022-dc` | Windows Server 2022 Datacenter | Windows |
| `windows-2022-dc-az` | Windows Server 2022 (Azure Edition) | Windows |
| `windows-2019-dc` | Windows Server 2019 Datacenter | Windows |

#### vmBatch Object Schema (Output Format)

The output transformation builds an array of batch objects:

```json
{
  "vmBatchName": "A",
  "vmCount": 2,
  "vmSize": "Standard_D4s_v6",
  "subnetIndex": 0,
  "vmImagePreset": "ubuntu-24-lts",
  "vmOSDiskSizeGB": 128,
  "vmOSDiskType": "StandardSSD_LRS",
  "vmOSDiskDeleteOption": "Delete"
}
```

#### Patching VM Batches from BOM

When patching defaults from BOM analysis:

**CRITICAL**: Azure Portal DropDown `defaultValue` must match the **LABEL**, not the VALUE.

1. Set `vmBatchCount.defaultValue` to number of batches from BOM
2. For each batch N (1-5), update field `defaultValue` properties using LABEL format:

```json
// Example: Patch batch 1 for 3 Windows VMs (using LABEL format)
{
  "batch1Section.batch1Name.defaultValue": "WebServers",
  "batch1Section.batch1Count.defaultValue": "3",
  "batch1Section.batch1Size.defaultValue": "Standard_D8s_v6 (8 vCPU, 32 GB)",
  "batch1Section.batch1Image.defaultValue": "Windows Server 2022 Datacenter",
  "batch1Section.batch1DiskSize.defaultValue": "256"
}
```

#### Preset Selection Logic (use LABEL format for defaultValue)

- BOM specifies "Windows" → use `Windows Server 2022 Datacenter`
- BOM specifies "Windows 2019" → use `Windows Server 2019 Datacenter`
- BOM specifies "Linux" or "Ubuntu" → use `Ubuntu 24.04 LTS`
- BOM specifies "Ubuntu 22" → use `Ubuntu 22.04 LTS`
- Default (OS not specified) → use `Ubuntu 24.04 LTS`

#### Dynamic Subnet Dropdowns

Multiple subnet dropdowns should be dynamically populated based on the network plan. This improves UX by showing subnet names instead of raw indices.

**Subnet Dropdown Elements:**

| Element | Step | Field Name | Visible When |
|---------|------|------------|--------------|
| VM Batch 1-5 | compute | `batch{N}Section.batch{N}Subnet` | vmBatchCount >= N |
| Load Balancer | networking | `loadBalancerSubnetIndex` | createLoadBalancer AND NOT loadBalancerPublic |

**Patching Requirements:**
1. Filter to only include subnets where `usage` equals "VM/PrivateEndpoint"
2. Display user-friendly labels: `{subnet-name} ({cidr})`
3. Value remains the subnet's 0-based index in the full array (as string)
4. Set `defaultValue` to the LABEL of the first available subnet

**Example allowedValues:**
```json
"allowedValues": [
  { "label": "snet-vm-01 (10.0.1.0/26)", "value": "1" },
  { "label": "snet-vm-02 (10.0.1.64/26)", "value": "2" }
],
"defaultValue": "snet-vm-01 (10.0.1.0/26)"
```

**Subnet Naming:**
- Use explicit names from network plan if available
- Otherwise generate: `snet-vm-{sequence}` (e.g., snet-vm-01, snet-vm-02)

### Resource Toggles (Yes/No Dropdowns)

- **Find by**: Look for DropDown elements with options `["Yes", "No"]`
- **Pattern**: Usually named like `createAKS`, `createAppService`, `createSQLMI`
- **Location**: Various steps based on resource category
- **Default format**: String `"Yes"` to enable, `"No"` to disable

## Element Identification Strategy

### Semantic Matching

When identifying elements to patch:

1. **Search labels first**: Most reliable - labels describe the element's purpose
2. **Check tooltips**: Tooltips often contain additional context
3. **Match name patterns**: Element names often follow conventions like `txtAuthorityId`
4. **Consider step context**: Networking elements are in networking steps

### Handling Ambiguity

If multiple elements could match:

1. Prefer elements in the expected step (basics for IDs, networking for network config)
2. Prefer elements with more specific labels
3. Report ambiguity in validation notes

## Output Format

When patching, generate a patch plan:

```json
{
  "patches": [
    {
      "step_name": "basics",
      "element_name": "txtAuthorityId",
      "default_value": "MIN01",
      "reasoning": "TextBox labeled 'Authority ID' in basics step"
    },
    {
      "step_name": "networking",
      "element_name": "subnetGrid",
      "default_value": [...],
      "reasoning": "EditableGrid for subnet configuration"
    }
  ],
  "validation_notes": "All elements found successfully"
}
```

## GSIS-Specific Patterns

### Expected Basics Elements

- Authority/Agency ID field
- Project ID field
- Environment selection (Dev/Test/Prod)

### Expected Networking Elements

- VNet address prefix field
- Subnet configuration grid
- DNS settings (if applicable)

### Expected Resource Toggle Naming

Toggle parameter names typically follow the pattern:

- `createAKS` - Azure Kubernetes Service
- `createAppService` - App Service
- `createSQLMI` - SQL Managed Instance
- `createCosmosDB` - Cosmos DB
- `createStorage` - Storage Account
- `createKeyVault` - Key Vault
- `createACR` - Azure Container Registry

## Validation Checklist

Before applying patches, verify:

- [ ] All target elements exist in the UI definition
- [ ] Element types match expected types (TextBox for text, DropDown for toggles)
- [ ] CIDR values are valid notation
- [ ] Subnet allocations fit within VNet prefix
- [ ] No duplicate subnet names
