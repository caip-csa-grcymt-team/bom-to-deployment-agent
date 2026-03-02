# GSIS Copilot CLI Integration

MCP servers and Copilot CLI integration for automating Azure infrastructure provisioning from Azure Pricing Calculator exports.

## Overview

This module provides:

- **MCP Servers**: Wrap existing GSIS services for use with GitHub Copilot CLI
- **Custom Agent**: Infrastructure planner agent with specialized skills
- **Skills**: Azure networking and UI definition patching expertise

## Prerequisites

- Python 3.12+
- GitHub Copilot CLI (`npm install -g @github/copilot`)
- GitHub PAT with Copilot permissions
- Azure credentials for IPAM access (optional for local testing)

## Installation

### 1. Install Python Dependencies

```powershell
# From repository root
cd copilot-cli
pip install -e .

# Also install the agent package for service access
cd ../agent
pip install -e .
```

### 2. Install Copilot CLI

```powershell
npm install -g @github/copilot
```

### 3. Authenticate

```powershell
# Set GitHub PAT
$env:GH_TOKEN = "ghp_your_token_here"

# Verify authentication
copilot --version
```

## Configuration

### MCP Server Configuration

Copy the example configuration and update paths:

```powershell
# Create Copilot config directory
mkdir -Force "$env:USERPROFILE\.copilot"

# Copy and customize configuration
Copy-Item copilot-cli\mcp-config.local.json.example "$env:USERPROFILE\.copilot\mcp-config.json"

# Edit the file to update:
# - cwd paths to your repository location
# - PYTHONPATH to agent/src
# - IPAM environment variables (if using IPAM)
```

### IPAM Configuration (Optional)

For IPAM integration, set these environment variables:

```powershell
$env:IPAM_FQDN = "ipam.yourdomain.com"
$env:IPAM_SPACE = "default"
$env:IPAM_BLOCK = "azure-production"
$env:IPAM_ENGINE_CLIENT_ID = "00000000-0000-0000-0000-000000000000"
```

## Local Testing

### Test BOM Parser

```powershell
# List available BOM files
copilot -p "List the BOM files available in the BOMs directory" --allow-all-tools

# Parse a specific BOM
copilot -p "Parse the BOM file at BOMs/2269-MIN69-RG169.xlsx and list the resources" --allow-all-tools
```

### Test with Custom Agent

```powershell
# Check available tools
copilot -p "List the tools you have access to" `
  --agent .github/agents/infra-planner.agent.md `
  --allow-all-tools

# Run full provisioning workflow
copilot -p "Provision infrastructure from BOMs/2269-MIN69-RG169.xlsx for authority MIN69 project RG169" `
  --agent .github/agents/infra-planner.agent.md `
  --allow-all-tools `
  --allow-all-paths
```

### Test Individual Components

```powershell
# Test BOM parsing
cd copilot-cli
python -c "from mcp.bom_server import create_server; print('BOM server OK')"

# Test IPAM config check (no credentials needed)
python -c "from mcp.ipam_server import create_server; print('IPAM server OK')"
```

## MCP Server Reference

### bom-parser

| Tool | Description | Required Args |
|------|-------------|---------------|
| `parse_bom` | Parse Excel BOM file | `excel_path` |
| `list_bom_files` | List available BOMs | (none) |

### ipam-client

| Tool | Description | Required Args |
|------|-------------|---------------|
| `reserve_cidr` | Reserve CIDR block | `authority_id`, `project_id`, `prefix_length` |
| `release_cidr` | Release reservation | `reservation_id` |
| `check_ipam_config` | Check configuration | (none) |

### ui-patcher

Provides deterministic JSON patching for createUiDefinition.json files.

| Tool | Description | Required Args |
|------|-------------|---------------|
| `patch_ui_definition` | Apply patches to UI definition | `patches` |
| `read_ui_element` | Read a specific element | `step_name`, `element_path` |
| `list_ui_steps` | List all steps and elements | (none) |

**Example patch call:**

```json
{
  "patches": [
    { "step_name": "basics", "element_path": "agency", "value": "MIN69" },
    { "step_name": "appGateway", "element_path": "appGatewaySku", "value": "WAF v2" }
  ],
  "output_path": "output/project/createUiDefinition.json"
}
```

## Skills Reference

### azure-networking

Provides expert knowledge on:

- Azure service subnet requirements
- Delegation requirements by service
- CIDR sizing calculations
- Network planning strategy

### ui-definition-patterns

Provides expert knowledge on:

- createUiDefinition.json structure
- Element identification strategies
- Patching rules for each value type
- GSIS-specific patterns

## Troubleshooting

### MCP Server Not Found

Ensure the mcp-config.json has correct paths:

```json
{
  "mcpServers": {
    "bom-parser": {
      "cwd": "C:/absolute/path/to/gsis-automation/copilot-cli"
    }
  }
}
```

### Import Errors

Ensure PYTHONPATH includes the agent src directory:

```powershell
$env:PYTHONPATH = "C:\path\to\gsis-automation\agent\src"
```

### Authentication Errors

Verify your GitHub PAT has the required permissions:

- `user_copilot_requests:read`
- `repo` (for file access)

### IPAM Connection Errors

1. Check environment variables with `check_ipam_config` tool
2. Verify Azure credentials with `az account show`
3. Ensure network access to IPAM endpoint

## File Structure

```
copilot-cli/
├── pyproject.toml              # Package configuration
├── mcp-config.template.json    # MCP config template for CI/CD
├── mcp-config.local.json.example  # Example local config
├── README.md                   # This file
├── SECRETS.md                  # Secrets documentation
└── mcp_servers/
    ├── __init__.py
    ├── bom_server.py           # BOM parser MCP server
    ├── ipam_server.py          # IPAM client MCP server
    └── ui_patcher_server.py    # UI definition patcher MCP server

.github/
├── agents/
│   └── infra-planner.agent.md  # Custom agent profile
├── prompts/
│   └── provision-environment.md  # Orchestration prompt
└── skills/
    ├── azure-networking.md     # Networking patterns skill
    └── ui-definition-patterns.md  # UI patching skill
```
