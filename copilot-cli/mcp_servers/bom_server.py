"""MCP server for parsing Azure Pricing Calculator BOM exports.

Wraps the existing ExcelParser service to expose BOM parsing capabilities
as MCP tools for use with GitHub Copilot CLI.

Environment Variables:
    WORKSPACE_ROOT: Path to the repository root (defaults to GITHUB_WORKSPACE or cwd)

Example:
    Start the server with:
        python -m mcp.bom_server

    Or use with Copilot CLI via mcp-config.json.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from services.excel_parser import ExcelParser, ExcelParserError

logger = logging.getLogger(__name__)


def _get_workspace_root() -> Path:
    """Get the workspace root directory.

    Checks environment variables in order: WORKSPACE_ROOT, GITHUB_WORKSPACE.
    Falls back to current working directory if neither is set.

    Returns:
        Path to the workspace root.
    """
    workspace = os.environ.get("WORKSPACE_ROOT") or os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        return Path(workspace).resolve()
    # Fall back to parent of copilot-cli directory (assumes we're running from copilot-cli)
    # This handles the case where cwd is copilot-cli/ but specs/ is at repo root
    cwd = Path.cwd()
    if cwd.name == "copilot-cli" and (cwd.parent / "specs").exists():
        return cwd.parent
    return cwd


def create_server() -> Server:
    """Create and configure the BOM parser MCP server.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("bom-parser")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="parse_bom",
                description=(
                    "Parse an Azure Pricing Calculator Excel export (BOM) file. "
                    "Returns raw content as pipe-separated lines and structured rows "
                    "extracted from the estimate sheet."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "excel_path": {
                            "type": "string",
                            "description": "Path to the Excel file (.xlsx) to parse",
                        },
                    },
                    "required": ["excel_path"],
                },
            ),
            Tool(
                name="list_bom_files",
                description=(
                    "List available BOM files in the specs directory. "
                    "Returns a list of Excel files that can be parsed."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "bom_directory": {
                            "type": "string",
                            "description": "Path to the directory containing BOM files (defaults to 'specs/')",
                            "default": "specs",
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool invocations."""
        if name == "parse_bom":
            return await _parse_bom(arguments)
        if name == "list_bom_files":
            return await _list_bom_files(arguments)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


async def _parse_bom(arguments: dict[str, Any]) -> list[TextContent]:
    """Parse a BOM Excel file.

    Args:
        arguments: Tool arguments containing excel_path.

    Returns:
        List with parsed content as TextContent.
    """
    excel_path = arguments.get("excel_path")
    if not excel_path:
        return [TextContent(type="text", text="Error: excel_path is required")]

    # Resolve path relative to workspace root if not absolute
    path = Path(excel_path)
    if not path.is_absolute():
        path = _get_workspace_root() / path
    path = path.resolve()

    if not path.exists():
        return [TextContent(type="text", text=f"Error: File not found: {path}")]

    try:
        parser = ExcelParser()
        result = parser.parse(path)

        # Format output for readability
        output_lines = [
            "# BOM Parse Results",
            "",
            f"**File**: {path.name}",
            f"**Structured Rows**: {len(result.get('structured_rows', []))}",
            "",
            "## Raw Content (First 50 lines)",
            "```",
        ]

        raw_lines = result.get("raw_content", "").split("\n")[:50]
        output_lines.extend(raw_lines)
        output_lines.append("```")

        if result.get("structured_rows"):
            output_lines.extend([
                "",
                "## Structured Resources",
                "",
            ])
            for row in result["structured_rows"][:20]:
                service = row.get("Service", row.get("service", "Unknown"))
                region = row.get("Region", row.get("region", "Unknown"))
                output_lines.append(f"- **{service}** (Region: {region})")

        return [TextContent(type="text", text="\n".join(output_lines))]

    except ExcelParserError as e:
        return [TextContent(type="text", text=f"Parse error: {e}")]
    except Exception as e:
        logger.exception("Unexpected error parsing BOM")
        return [TextContent(type="text", text=f"Unexpected error: {e}")]


async def _list_bom_files(arguments: dict[str, Any]) -> list[TextContent]:
    """List available BOM files.

    Args:
        arguments: Tool arguments containing optional bom_directory.

    Returns:
        List with available files as TextContent.
    """
    # Resolve directory relative to workspace root if not absolute
    bom_dir_arg = arguments.get("bom_directory", "specs")
    bom_dir = Path(bom_dir_arg)
    if not bom_dir.is_absolute():
        bom_dir = _get_workspace_root() / bom_dir
    bom_dir = bom_dir.resolve()

    if not bom_dir.exists():
        return [TextContent(type="text", text=f"Directory not found: {bom_dir}")]

    xlsx_files = list(bom_dir.glob("*.xlsx"))

    if not xlsx_files:
        return [TextContent(type="text", text=f"No Excel files found in {bom_dir}")]

    output_lines = [
        "# Available BOM Files",
        "",
        f"**Directory**: {bom_dir}",
        "",
    ]

    for f in sorted(xlsx_files):
        size_kb = f.stat().st_size / 1024
        output_lines.append(f"- `{f.name}` ({size_kb:.1f} KB)")

    return [TextContent(type="text", text="\n".join(output_lines))]


async def main() -> None:
    """Run the BOM parser MCP server."""
    logging.basicConfig(level=logging.INFO)
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
