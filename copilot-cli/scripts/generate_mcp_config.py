#!/usr/bin/env python3
"""
Generate MCP configuration for Copilot CLI in CI/CD environment.

This script creates a JSON configuration file for MCP servers that works
with the GitHub Copilot CLI's --additional-mcp-config option.

Environment Variables Required:
  - GITHUB_WORKSPACE: Base path to the repository
  - PYTHON_CMD: Full path to the Python interpreter

Environment Variables for IPAM (Optional):
  - IPAM_FQDN, IPAM_SPACE, IPAM_BLOCK
  - IPAM_ENGINE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_ID
"""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    """Generate MCP configuration file."""
    # Get workspace from environment or use current directory
    workspace = os.environ.get("GITHUB_WORKSPACE", os.getcwd())

    # Get Python command - prefer PYTHON_CMD env var, fall back to sys.executable
    python_cmd = os.environ.get("PYTHON_CMD", sys.executable)

    # Construct the copilot-cli path
    copilot_cli_path = os.path.join(workspace, "copilot-cli")

    # Build the MCP configuration
    config = {
        "mcpServers": {
            "bom-parser": {
                "command": python_cmd,
                "args": ["-m", "mcp_servers.bom_server"],
                "cwd": copilot_cli_path,
                "env": {
                    "PYTHONPATH": copilot_cli_path,
                    "WORKSPACE_ROOT": workspace,
                },
            },
            "ipam-client": {
                "command": python_cmd,
                "args": ["-m", "mcp_servers.ipam_server"],
                "cwd": copilot_cli_path,
                "env": {
                    "PYTHONPATH": copilot_cli_path,
                    "IPAM_FQDN": os.environ.get("IPAM_FQDN", ""),
                    "IPAM_SPACE": os.environ.get("IPAM_SPACE", ""),
                    "IPAM_BLOCK": os.environ.get("IPAM_BLOCK", ""),
                    "IPAM_ENGINE_CLIENT_ID": os.environ.get("IPAM_ENGINE_CLIENT_ID", ""),
                    "AZURE_TENANT_ID": os.environ.get("AZURE_TENANT_ID", ""),
                    "AZURE_CLIENT_ID": os.environ.get("AZURE_CLIENT_ID", ""),
                },
            },
            "ui-patcher": {
                "command": python_cmd,
                "args": ["-m", "mcp_servers.ui_patcher_server"],
                "cwd": copilot_cli_path,
                "env": {
                    "PYTHONPATH": copilot_cli_path,
                    "WORKSPACE_ROOT": workspace,
                },
            },
        }
    }

    # Ensure .copilot directory exists in workspace root
    output_dir = Path(workspace) / ".copilot"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write the configuration file
    output_file = output_dir / "mcp-config.json"
    with open(output_file, "w") as f:
        json.dump(config, f, indent=2)

    print(f"MCP config generated successfully at: {output_file}")
    print(f"  Python command: {python_cmd}")
    print(f"  Copilot CLI path: {copilot_cli_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
