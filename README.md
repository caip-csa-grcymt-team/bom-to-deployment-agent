# BOM to Deployment Agent

Automated Azure infrastructure provisioning from Azure Pricing Calculator exports (BOMs). Two AI agents — powered by GitHub Copilot CLI — parse BOM spreadsheets, plan network topology, reserve IP address space, generate Azure Verified Module (AVM) Bicep templates, and deploy infrastructure with private-only access.

## Features

- **BOM Parsing** — Extracts Azure resources, SKUs, regions, and quantities from Azure Pricing Calculator Excel exports
- **Network Planning** — Automatically determines subnet sizes, VNet capacity, and delegation requirements based on identified resources
- **IPAM Integration** — Reserves CIDR blocks from Azure IPAM to prevent address space conflicts
- **AVM-Based Bicep Generation** — Generates `main.bicep` using Azure Verified Modules with dynamic module discovery and version resolution
- **Private Access by Default** — All resources deployed with Private Endpoints or VNet integration; public network access disabled
- **CAF Naming Convention** — Resources named following Cloud Adoption Framework standards with configurable environment and region codes
- **GitHub Actions CI/CD** — Fully automated pipeline from BOM upload to infrastructure deployment
- **Multi-Environment Support** — Deploy to dev, stg, or prd environments with consistent naming and configuration

## Architecture

The solution uses a two-agent architecture orchestrated by a GitHub Actions workflow:

<!-- Architecture diagram placeholder — add diagram image here -->

### Agents

| Agent | Description | Inputs | Outputs |
|-------|-------------|--------|---------|
| **infra-planner** | Parses BOM, plans network topology, reserves IPAM CIDR, allocates subnets | `.xlsx` spec file | `resources.json`, `network-plan.json`, `vnet-params.json` |
| **infra-provisioner** | Resolves AVM modules, generates Bicep with private access and naming conventions | Planner JSON outputs | `main.bicep`, `main.bicepparam` |

### MCP Servers

| Server | Purpose |
|--------|---------|
| **bom-parser** | Parses Azure Pricing Calculator Excel exports |
| **ipam-client** | Reserves and releases CIDR blocks from Azure IPAM |
| **avm-resolver** | Resolves ARM resource types to versioned AVM Bicep module references |

### Instruction Files

| File | Purpose |
|------|---------|
| `copilot-cli/instructions/avm-discovery.instructions.md` | AVM module discovery algorithm with edge cases and fallback strategy |
| `copilot-cli/instructions/naming-convention.instructions.md` | CAF-based resource naming rules with resource-specific overrides |
| `copilot-cli/instructions/private-access.instructions.md` | Private Endpoint and VNet integration patterns with DNS zone inventory |

## Workflow

The GitHub Actions workflow (`provision-infrastructure-v2.yml`) executes the following stages:

1. **Setup** — Parse spec filename, derive application name, environment code, and resource group name
2. **Create Resource Group** — Create or verify the target resource group in Azure
3. **Install Tools** — Set up Node.js, Python, Copilot CLI, and MCP server dependencies
4. **Run Infra Planner** — Execute the planner agent to parse the BOM, plan networking, and reserve IPAM space
5. **Run Infra Provisioner** — Execute the provisioner agent to generate AVM-based Bicep templates
6. **Validate Bicep** — Compile Bicep, restore AVM modules, and run a what-if deployment preview
7. **Deploy Infrastructure** — Deploy the generated Bicep template using incremental mode

## Project Structure

```
.github/
├── agents/
│   ├── infra-planner.agent.md         # Planner agent definition
│   └── infra-provisioner.agent.md     # Provisioner agent definition
└── workflows/
    └── provision-infrastructure-v2.yml # GitHub Actions workflow

copilot-cli/
├── instructions/                      # Agent instruction files
│   ├── avm-discovery.instructions.md
│   ├── naming-convention.instructions.md
│   └── private-access.instructions.md
├── mcp_servers/                       # MCP tool servers
│   ├── bom_server.py                  # BOM Excel parser
│   ├── ipam_server.py                 # Azure IPAM client
│   └── avm_resolver_server.py         # AVM module resolver
├── services/                          # Shared service modules
├── scripts/                           # Utility scripts
├── tests/                             # Unit tests
├── PROMPT_TEMPLATE.txt                # Planner agent prompt
├── PROVISIONER_PROMPT_TEMPLATE.txt    # Provisioner agent prompt
├── OUTPUT_SCHEMAS.md                  # Planner output contract
└── PROVISIONER_OUTPUT_SCHEMAS.md      # Provisioner output contract

specs/                                 # BOM Excel files (input)
output/                                # Generated artifacts (runtime)
```

## Prerequisites

- Python 3.12+
- Node.js 20+
- GitHub Copilot license (organization-level, for Copilot CLI)
- Azure subscription with Contributor access
- Azure IPAM instance (for CIDR reservation)

## Configuration

### Azure

#### User-Assigned Managed Identity

Create a UAMI for GitHub Actions OIDC authentication:

```bash
az identity create \
  --name "uami-gsis-github-actions" \
  --resource-group "<identity-rg>" \
  --location "westeurope"
```

#### Federated Credential

Add a federated credential for GitHub Actions OIDC:

```bash
az identity federated-credential create \
  --name "github-actions-main" \
  --identity-name "uami-gsis-github-actions" \
  --resource-group "<identity-rg>" \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:caip-csa-grcymt-team/bom-to-deployment-agent:ref:refs/heads/main" \
  --audiences "api://AzureADTokenExchange"
```

#### RBAC

Assign Contributor role on the target subscription:

```bash
UAMI_PRINCIPAL_ID=$(az identity show \
  --name "uami-gsis-github-actions" \
  --resource-group "<identity-rg>" \
  --query principalId -o tsv)

az role assignment create \
  --assignee-object-id "$UAMI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Contributor" \
  --scope "/subscriptions/<subscription-id>"
```

### GitHub Secrets

Configure in **Settings → Secrets and variables → Actions → Secrets**:

| Secret | Description |
|--------|-------------|
| `AZURE_CLIENT_ID` | UAMI client ID |
| `AZURE_TENANT_ID` | Entra ID tenant ID |
| `COPILOT_TOKEN` | GitHub Copilot API token |
| `IPAM_ENGINE_CLIENT_ID` | IPAM service identity client ID |

### GitHub Variables

Configure in **Settings → Secrets and variables → Actions → Variables**:

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_SUBSCRIPTION_ID` | Target Azure subscription | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `IPAM_FQDN` | Azure IPAM endpoint | `ipam.yourdomain.com` |
| `IPAM_SPACE` | IPAM address space name | `default` |
| `IPAM_BLOCK` | IPAM CIDR block name | `westeurope-block` |

## Usage

### 1. Add a BOM Spec File

Place an Azure Pricing Calculator export (`.xlsx`) in the `specs/` directory. The filename must follow the format:

```
<project-number>-<authority-id>-<project-id>.xlsx
```

Example: `2269-MIN69-RG170.xlsx`

### 2. Trigger the Workflow

Go to **Actions → Provision Infrastructure v2 (AVM) → Run workflow** and fill in:

| Input | Description | Example |
|-------|-------------|---------|
| Spec file | Filename from `specs/` | `2269-MIN69-RG170.xlsx` |
| Environment | Target environment | `dev` / `stg` / `prd` |
| Location | Azure region | `westeurope` |

### 3. Monitor Execution

The workflow produces a step summary with status for each stage. Artifacts (planner outputs, generated Bicep, agent logs) are uploaded and available for 30 days.

## Local Development

### Install Dependencies

```bash
cd copilot-cli
pip install -e ".[dev]"
```

### Run Tests

```bash
cd copilot-cli
pytest tests/ -v
```

### Lint

```bash
cd copilot-cli
ruff check .
ruff format --check .
```

## License

Internal use only.
