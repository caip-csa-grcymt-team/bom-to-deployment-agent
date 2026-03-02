---
description: "Dynamic AVM module discovery algorithm, registry conventions, edge cases, and fallback strategy for the infra-provisioner agent"
applyTo: "copilot-cli/**"
---

## Scope

This instruction file defines how the `infra-provisioner` agent resolves ARM resource types to Azure Verified Module (AVM) Bicep references. Apply these rules when generating `main.bicep` to select the correct AVM module for each resource.

## Resolution Fallback Order

Follow this priority when resolving an ARM resource type to an AVM module reference:

1. `avm-resolver` MCP tool (preferred): call `resolve_module` with the ARM type. Accept the returned path and version.
2. Deterministic algorithm (offline fallback): apply the ARM-to-AVM conversion described below.
3. Manual specification: if both fail, document the ARM type with a `// TODO: resolve AVM module` comment.

## Module Reference Format

AVM Bicep modules are referenced with the `br/public:` alias:

```text
br/public:avm/res/{provider}/{type}:{version}
```

Equivalent full registry path (not recommended):

```text
br:mcr.microsoft.com/bicep/avm/res/{provider}/{type}:{version}
```

Always prefer the `br/public:` alias in generated Bicep.

## Version Resolution

When the `avm-resolver` MCP tool is available, accept its resolved version. When generating without tools, use `0.x.x` as a placeholder and add a comment:

```bicep
// TODO: pin to latest AVM version — run `avm-resolver resolve_module` or check https://aka.ms/avm/index/bicep/res/csv
module storageAccount 'br/public:avm/res/storage/storage-account:0.x.x' = { /* ... */ }
```

## Deterministic ARM-to-AVM Algorithm

### Conversion Steps

```text
Input:  Microsoft.{ProviderName}/{ResourceTypes}
Output: avm/res/{provider-kebab}/{resource-kebab-singular}
```

1. Split the ARM type on the first `/`.
2. Strip the `Microsoft.` prefix from the provider namespace.
3. Convert PascalCase to kebab-case (insert `-` before each uppercase letter that follows a lowercase letter or digit).
4. Singularize the resource type segment:
   - If it ends with `ies`, replace with `y` (e.g., `registries` becomes `registry`).
   - If it ends with `ses`, remove `es` (e.g., `databases` becomes `database`).
   - If it ends with `s` (and not `ss`), remove the trailing `s`.
5. Assemble the path: `avm/res/{provider-kebab}/{resource-kebab-singular}`.

### Pseudocode

```python
import re

def arm_type_to_avm_path(arm_type: str) -> str:
    parts = arm_type.split("/")
    provider = parts[0].replace("Microsoft.", "")
    resource = parts[1]

    def to_kebab(s: str) -> str:
        return re.sub(r'(?<=[a-z0-9])([A-Z])', r'-\1', s).lower()

    provider_kebab = to_kebab(provider)
    resource_kebab = to_kebab(resource)

    # Singularize
    if resource_kebab.endswith("ies"):
        resource_kebab = resource_kebab[:-3] + "y"
    elif resource_kebab.endswith("ses"):
        resource_kebab = resource_kebab[:-2]
    elif resource_kebab.endswith("s") and not resource_kebab.endswith("ss"):
        resource_kebab = resource_kebab[:-1]

    return f"avm/res/{provider_kebab}/{resource_kebab}"
```

## Known Edge Cases

The deterministic algorithm handles most cases. These non-standard mappings require special attention:

| ARM Resource Type | Expected AVM Path | Notes |
|---|---|---|
| `Microsoft.DocumentDB/databaseAccounts` | `avm/res/document-db/database-account` | Provider abbreviation uses `DB` not `Db` |
| `Microsoft.ContainerService/managedClusters` | `avm/res/container-service/managed-cluster` | Two-word provider and resource |
| `Microsoft.DBforMySQL/flexibleServers` | `avm/res/db-for-my-sql/flexible-server` | Mixed-case `DB` and camelCase provider |
| `Microsoft.DBforPostgreSQL/flexibleServers` | `avm/res/db-for-postgre-sql/flexible-server` | Mixed-case with `SQL` |
| `Microsoft.OperationalInsights/workspaces` | `avm/res/operational-insights/workspace` | Long provider name |
| `Microsoft.ContainerRegistry/registries` | `avm/res/container-registry/registry` | `-ies` to `-y` singularization |
| `Microsoft.ManagedIdentity/userAssignedIdentities` | `avm/res/managed-identity/user-assigned-identity` | Deeply compound resource |
| `Microsoft.ApiManagement/service` | `avm/res/api-management/service` | Resource is already singular |
| `Microsoft.Cache/redis` | `avm/res/cache/redis` | Resource is already singular |
| `Microsoft.Web/sites` | `avm/res/web/site` | Simple singularization |

## Verified Standard Mappings

| ARM Resource Type | AVM Module Path |
|---|---|
| `Microsoft.Storage/storageAccounts` | `avm/res/storage/storage-account` |
| `Microsoft.KeyVault/vaults` | `avm/res/key-vault/vault` |
| `Microsoft.Network/virtualNetworks` | `avm/res/network/virtual-network` |
| `Microsoft.Network/privateDnsZones` | `avm/res/network/private-dns-zone` |
| `Microsoft.Sql/servers` | `avm/res/sql/server` |
| `Microsoft.Compute/virtualMachines` | `avm/res/compute/virtual-machine` |
| `Microsoft.Web/serverfarms` | `avm/res/web/serverfarm` |
| `Microsoft.CognitiveServices/accounts` | `avm/res/cognitive-services/account` |
| `Microsoft.Search/searchServices` | `avm/res/search/search-service` |
| `Microsoft.EventHub/namespaces` | `avm/res/event-hub/namespace` |
| `Microsoft.Insights/components` | `avm/res/insights/component` |
| `Microsoft.App/managedEnvironments` | `avm/res/app/managed-environment` |
| `Microsoft.App/containerApps` | `avm/res/app/container-app` |
| `Microsoft.Network/applicationGateways` | `avm/res/network/application-gateway` |
| `Microsoft.Network/bastionHosts` | `avm/res/network/bastion-host` |
| `Microsoft.Network/azureFirewalls` | `avm/res/network/azure-firewall` |
| `Microsoft.Network/natGateways` | `avm/res/network/nat-gateway` |
| `Microsoft.Network/loadBalancers` | `avm/res/network/load-balancer` |

## Child Resource Handling

ARM child resource types (e.g., `Microsoft.KeyVault/vaults/secrets`, `Microsoft.Sql/servers/databases`) do not have their own standalone AVM modules. They are configured as parameters on the parent module.

| ARM Child Type | Parent AVM Module | Configuration |
|---|---|---|
| `Microsoft.KeyVault/vaults/secrets` | `avm/res/key-vault/vault` | Use `secrets` parameter array |
| `Microsoft.Sql/servers/databases` | `avm/res/sql/server` | Use `databases` parameter array |
| `Microsoft.EventHub/namespaces/eventHubs` | `avm/res/event-hub/namespace` | Use `eventhubs` parameter array |

Do not attempt to resolve child resources to separate AVM modules. Nest them within their parent module invocation.

## CSV Index Reference

The AVM CSV index provides a machine-readable mapping of all published AVM resource modules:

```text
https://aka.ms/avm/index/bicep/res/csv
```

Columns: `ProviderNamespace`, `ResourceType`, `ModuleName`, `ModuleStatus`, `PublicRegistryReference`, `Description`.

Use this index for bulk validation or when the MCP tool is unavailable.
