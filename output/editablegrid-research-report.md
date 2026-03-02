# EditableGrid Limitation Research Report

## Azure createUiDefinition.json VM Batch Configuration

**Date:** February 17, 2026  
**Context:** GSIS Provisioning System - Template Spec UI for VM Batch Configuration

---

## Executive Summary

Research confirms that `Microsoft.Common.EditableGrid` does **NOT** support pre-populated default row values. This is a fundamental design limitation of the control. This report evaluates five alternative approaches with recommendations.

---

## 1. Confirmation of EditableGrid Limitation

### Official Documentation Analysis

The [Microsoft.Common.EditableGrid documentation](https://learn.microsoft.com/azure/azure-resource-manager/managed-applications/microsoft-common-editablegrid) shows the following schema:

```json
{
  "name": "people",
  "type": "Microsoft.Common.EditableGrid",
  "ariaLabel": "Enter information per person",
  "label": "People",
  "constraints": {
    "width": "Full",
    "rows": {
      "count": {
        "min": 1,
        "max": 10
      }
    },
    "columns": [...]
  }
}
```

**Key Findings:**

| Property | Supported | Notes |
|----------|-----------|-------|
| `defaultValue` | ❌ **NO** | Not listed in schema or documentation |
| `name` | ✅ Yes | Internal identifier |
| `label` | ✅ Yes | Display text |
| `ariaLabel` | ✅ Yes | Accessibility label |
| `constraints.rows.count` | ✅ Yes | Min/max row limits only |
| `constraints.columns` | ✅ Yes | Column definitions |

### Evidence

1. **Schema Definition**: The official schema does not include a `defaultValue` property
2. **Documentation Remarks**: No mention of pre-populating rows
3. **Control Design**: EditableGrid is designed for user-driven row creation
4. **Column Elements**: Only `TextBox`, `OptionsGroup`, and `DropDown` are supported within columns

### Source

- [Microsoft.Common.EditableGrid - Azure Documentation](https://learn.microsoft.com/azure/azure-resource-manager/managed-applications/microsoft-common-editablegrid)

---

## 2. Alternative Approaches

### Approach A: Fixed Maximum Sections Pattern

**Description**: Replace EditableGrid with N pre-defined `Microsoft.Common.Section` blocks (e.g., 5 VM batch sections), each containing individual controls for batch configuration. Use a slider to enable/disable sections.

```json
{
  "name": "vmBatchCount",
  "type": "Microsoft.Common.Slider",
  "min": 0,
  "max": 5,
  "defaultValue": 2,
  "label": "Number of VM Batches"
},
{
  "name": "batch1",
  "type": "Microsoft.Common.Section",
  "label": "VM Batch 1",
  "visible": "[greater(steps('compute').vmBatchCount, 0)]",
  "elements": [
    {
      "name": "vmBatchName",
      "type": "Microsoft.Common.TextBox",
      "label": "Batch Name",
      "defaultValue": "BatchA"
    },
    {
      "name": "vmCount",
      "type": "Microsoft.Common.DropDown",
      "defaultValue": { "value": 2 },
      "constraints": { "allowedValues": [...] }
    }
    // ... other controls
  ]
}
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| **Default Value Support** | ✅ Excellent | Each control supports `defaultValue` |
| **Implementation Complexity** | ⚠️ Medium | ~150-200 lines per batch × 5 = ~750-1000 lines |
| **UX Quality** | ✅ Good | Clean sections, conditional visibility |
| **Maintainability** | ⚠️ Medium | Repetitive code, harder to modify |
| **Pre-fill from BOM** | ⚠️ Manual | Requires regenerating createUiDefinition |

---

### Approach B: InfoBox Display + Manual Entry Pattern

**Description**: Display computed/recommended values in an `InfoBox` element, then have users manually enter values into standard controls.

```json
{
  "name": "bomRecommendation",
  "type": "Microsoft.Common.InfoBox",
  "visible": true,
  "options": {
    "icon": "Info",
    "text": "BOM Analysis recommends:\n• Batch A: 3× Standard_D4s_v6\n• Batch B: 2× Standard_D8s_v6\n\nPlease configure the batches below with these values."
  }
}
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| **Default Value Support** | ❌ None | Display only - no data binding |
| **Implementation Complexity** | ✅ Low | Simple InfoBox + existing controls |
| **UX Quality** | ⚠️ Poor | Users must manually copy values |
| **Maintainability** | ✅ High | Simple text update |
| **Pre-fill from BOM** | ⚠️ Partial | Shows values but doesn't populate |

---

### Approach C: ArmApiControl with Dynamic Defaults

**Description**: Use `Microsoft.Solutions.ArmApiControl` to fetch configuration from an external API, then use the results to populate dropdown `allowedValues` or other controls.

```json
{
  "name": "getBomConfig",
  "type": "Microsoft.Solutions.ArmApiControl",
  "request": {
    "method": "GET",
    "path": "[concat('/subscriptions/', subscription().subscriptionId, '/resourceGroups/config-rg/providers/Microsoft.Storage/storageAccounts/configstore/blobServices/default/containers/bom/blobs/', basics('requestNumber'), '?api-version=2021-04-01')]"
  }
}
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| **Default Value Support** | ⚠️ Limited | Can populate dropdowns, not EditableGrid rows |
| **Implementation Complexity** | ❌ High | Requires API endpoint, auth, CORS handling |
| **UX Quality** | ✅ Good | Dynamic population feels native |
| **Maintainability** | ⚠️ Medium | External dependency |
| **Pre-fill from BOM** | ⚠️ Partial | Works for simple values, not arrays |

---

### Approach D: Template Spec URL with Parameters

**Description**: Generate a deployment URL with parameters encoded, bypassing the createUiDefinition entirely.

```
https://portal.azure.com/#create/Microsoft.Template/templateSpecVersionId/
%2fsubscriptions%2f{sub}%2f...
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| **Default Value Support** | ❌ Not Supported | URL format doesn't support parameter injection for createUiDefinition |
| **Implementation Complexity** | N/A | Not viable |
| **UX Quality** | N/A | Not viable |
| **Pre-fill from BOM** | ❌ No | Azure Portal URL doesn't support query params for UI pre-fill |

**Finding**: Azure Template Spec deployment URLs do not support passing parameter values through query strings to pre-fill the createUiDefinition UI. This approach is **not viable**.

---

### Approach E: Hybrid Repeatable Sections with Computed Visibility

**Description**: Create a batch count slider and N pre-defined sections. Use createUiDefinition expressions to dynamically show/hide sections and pre-populate defaults.

```json
{
  "name": "vmBatchCount",
  "type": "Microsoft.Common.Slider",
  "min": 0,
  "max": 5,
  "defaultValue": 2,
  "label": "Number of VM Batches"
},
{
  "name": "batch1Section",
  "type": "Microsoft.Common.Section",
  "label": "VM Batch 1",
  "visible": "[greaterOrEquals(steps('compute').vmBatchCount, 1)]",
  "elements": [
    {
      "name": "batch1Name",
      "type": "Microsoft.Common.TextBox",
      "label": "Batch Name",
      "defaultValue": "A",
      "constraints": { "required": true }
    },
    {
      "name": "batch1Count",
      "type": "Microsoft.Common.DropDown",
      "label": "VM Count",
      "defaultValue": "2",
      "constraints": {
        "allowedValues": [
          { "label": "1", "value": "1" },
          { "label": "2", "value": "2" },
          { "label": "3", "value": "3" },
          { "label": "4", "value": "4" },
          { "label": "5", "value": "5" }
        ]
      }
    }
    // ... additional controls
  ]
}
```

**Output transformation in outputs section:**

```json
"outputs": {
  "vmBatches": "[if(equals(steps('compute').vmBatchCount, 0), 
    createArray(),
    if(equals(steps('compute').vmBatchCount, 1),
      createArray(createObject('vmBatchName', steps('compute').batch1Section.batch1Name, ...)),
      if(equals(steps('compute').vmBatchCount, 2),
        createArray(...batch1, ...batch2),
        ...
      )
    )
  )]"
}
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| **Default Value Support** | ✅ Excellent | Full control over defaults |
| **Implementation Complexity** | ⚠️ Medium-High | Verbose, but straightforward |
| **UX Quality** | ✅ Good | Progressive disclosure via slider |
| **Maintainability** | ⚠️ Medium | Repetitive but predictable |
| **Pre-fill from BOM** | ✅ Good | Generate createUiDefinition with defaults |

---

## 3. Comparison Matrix

| Approach | Default Support | Implementation | UX Quality | BOM Pre-fill | Recommended |
|----------|-----------------|----------------|------------|--------------|-------------|
| **A: Fixed Sections** | ✅ Excellent | ⚠️ Medium | ✅ Good | ⚠️ Manual | ⭐⭐⭐⭐ |
| **B: InfoBox + Manual** | ❌ None | ✅ Low | ❌ Poor | ⚠️ Partial | ⭐⭐ |
| **C: ArmApiControl** | ⚠️ Limited | ❌ High | ✅ Good | ⚠️ Partial | ⭐⭐⭐ |
| **D: URL Parameters** | ❌ Not Viable | N/A | N/A | ❌ No | ❌ |
| **E: Hybrid Sections** | ✅ Excellent | ⚠️ Medium-High | ✅ Good | ✅ Good | ⭐⭐⭐⭐⭐ |

---

## 4. Recommended Approach

### Primary Recommendation: Approach E - Hybrid Repeatable Sections

**Justification:**

1. **Full Default Value Control**: Each individual control (TextBox, DropDown, Slider) supports `defaultValue`
2. **Progressive Disclosure**: Slider controls visibility, showing only relevant sections
3. **BOM Integration**: Automation pipeline can generate createUiDefinition.json with project-specific defaults
4. **ARM Template Compatibility**: Output transformation produces array format compatible with existing Bicep modules
5. **User Experience**: Clean UI with collapsible sections and clear visual hierarchy

### Implementation Strategy

1. **Maximum Batches**: Support up to 5 VM batches (matches current EditableGrid max)
2. **Slider Control**: `vmBatchCount` slider (0-5) controls section visibility
3. **Section Structure**: Each section contains:
   - Batch Name (TextBox)
   - VM Count (DropDown 1-5)
   - VM Size (DropDown)
   - Subnet Index (DropDown)
   - OS Image Preset (DropDown)
   - OS Disk Size (DropDown)
   - OS Disk Type (DropDown)
   - OS Disk Delete Option (DropDown)
4. **Output Transformation**: Build array in outputs section using conditional expressions

### Implementation Complexity Estimate

| Task | Effort |
|------|--------|
| Design section schema | 2 hours |
| Implement 5 batch sections | 4-6 hours |
| Output transformation logic | 2 hours |
| Testing & validation | 2 hours |
| **Total** | **10-12 hours** |

---

## 5. UX Impact Analysis

### Current State (EditableGrid)

- ❌ Empty grid on load
- ❌ User must click "Add row" for each batch
- ❌ No guidance on recommended values
- ✅ Compact layout
- ✅ Dynamic row count

### Proposed State (Hybrid Sections)

- ✅ Pre-populated with recommended defaults
- ✅ Slider provides intuitive batch count selection
- ✅ Individual controls support field-level validation
- ⚠️ Fixed maximum (5 batches)
- ⚠️ More vertical space required

### User Journey Comparison

| Step | EditableGrid | Hybrid Sections |
|------|--------------|-----------------|
| 1 | View empty grid | View slider showing "2 batches" |
| 2 | Click "Add row" | See pre-filled Batch 1 & 2 sections |
| 3 | Fill 8 fields | Verify/modify pre-filled values |
| 4 | Click "Add row" again | Increase slider if more batches needed |
| 5 | Fill 8 more fields | Fill new section |
| **Total Clicks** | 2 + (8×N fields) | 0-N slider + modifications |

---

## 6. Automation Integration

### BOM-to-UI Pipeline Enhancement

The automation pipeline can generate a project-specific `createUiDefinition.json` with pre-filled defaults:

```python
def generate_ui_definition(bom_resources: List[VMBatchConfig]) -> dict:
    """Generate createUiDefinition.json with BOM defaults."""
    sections = []
    for i, batch in enumerate(bom_resources[:5], 1):
        sections.append({
            "name": f"batch{i}Section",
            "type": "Microsoft.Common.Section",
            "label": f"VM Batch {i}",
            "visible": f"[greaterOrEquals(steps('compute').vmBatchCount, {i})]",
            "elements": [
                {
                    "name": f"batch{i}Name",
                    "type": "Microsoft.Common.TextBox",
                    "label": "Batch Name",
                    "defaultValue": batch.name  # From BOM
                },
                {
                    "name": f"batch{i}Count",
                    "type": "Microsoft.Common.DropDown",
                    "defaultValue": str(batch.vm_count),  # From BOM
                    # ...
                }
            ]
        })
    return {"sections": sections, "defaultBatchCount": len(bom_resources)}
```

---

## 7. Alternative Considerations

### If More Than 5 Batches Required

If future requirements exceed 5 batches:
1. Deploy VMs in multiple phases
2. Use ARM template directly (bypassing createUiDefinition)
3. Consider Azure Portal custom deployment blade

### If Dynamic Configuration Required

If configuration must be fetched at runtime:
1. Combine ArmApiControl with sections
2. Use outputs from ArmApiControl as `defaultValue` expressions
3. Requires external configuration storage (Azure Storage, KeyVault)

---

## 8. Conclusion

The `Microsoft.Common.EditableGrid` control **does not support default values** for row data. The recommended alternative is the **Hybrid Repeatable Sections** approach (Approach E), which provides:

- Full control over default values
- Good user experience with progressive disclosure
- Compatibility with BOM automation pipeline
- Reasonable implementation complexity (~10-12 hours)

This approach requires refactoring the VM batch configuration section of `createUiDefinition.json` but maintains compatibility with existing Bicep modules through output transformation.

---

## References

- [Microsoft.Common.EditableGrid Documentation](https://learn.microsoft.com/azure/azure-resource-manager/managed-applications/microsoft-common-editablegrid)
- [CreateUiDefinition Elements Reference](https://learn.microsoft.com/azure/azure-resource-manager/managed-applications/create-uidefinition-elements)
- [CreateUiDefinition Functions](https://learn.microsoft.com/azure/azure-resource-manager/managed-applications/create-uidefinition-functions)
- [Microsoft.Common.Section](https://learn.microsoft.com/azure/azure-resource-manager/managed-applications/microsoft-common-section)
- [Microsoft.Common.Slider](https://learn.microsoft.com/azure/azure-resource-manager/managed-applications/microsoft-common-slider)
- [Microsoft.Solutions.ArmApiControl](https://learn.microsoft.com/azure/azure-resource-manager/managed-applications/microsoft-solutions-armapicontrol)
