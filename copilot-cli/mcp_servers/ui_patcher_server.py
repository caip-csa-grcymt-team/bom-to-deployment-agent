"""MCP server for patching createUiDefinition.json files.

Provides deterministic JSON patching for Azure Portal UI definition files.
Supports deep property updates and dropdown allowedValues modifications.

Environment Variables:
    WORKSPACE_ROOT: Path to the repository root (defaults to GITHUB_WORKSPACE or cwd)

Example:
    Start the server with:
        python -m mcp_servers.ui_patcher_server

    Or use with Copilot CLI via mcp-config.json.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

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
    cwd = Path.cwd()
    if cwd.name == "copilot-cli" and (cwd.parent / "createUiDefinition.json").exists():
        return cwd.parent
    return cwd


def _resolve_path(path_str: str) -> Path:
    """Resolve a path relative to workspace root if not absolute."""
    path = Path(path_str)
    if not path.is_absolute():
        path = _get_workspace_root() / path
    return path.resolve()


def _find_element_by_name(
    elements: list[dict], name: str, step_name: str | None = None
) -> dict | None:
    """Recursively find an element by name within a UI definition structure.

    Args:
        elements: List of UI elements to search.
        name: Element name to find.
        step_name: Optional step name to search within.

    Returns:
        The found element dict, or None.
    """
    for element in elements:
        if element.get("name") == name:
            return element
        # Search within Section elements
        if element.get("type") == "Microsoft.Common.Section":
            nested = element.get("elements", [])
            found = _find_element_by_name(nested, name, step_name)
            if found:
                return found
    return None


def _find_element_in_steps(
    ui_def: dict, step_name: str, element_path: str
) -> dict | None:
    """Find an element within a specific step.

    Args:
        ui_def: The full UI definition dict.
        step_name: Name of the step (e.g., 'networking', 'compute').
        element_path: Dot-separated path to element (e.g., 'batch1Section.batch1Size').

    Returns:
        The found element dict, or None.
    """
    steps = ui_def.get("view", {}).get("properties", {}).get("steps", [])

    # Find the step
    target_step = None
    for step in steps:
        if step.get("name") == step_name:
            target_step = step
            break

    if not target_step:
        return None

    # Parse element path (supports nested sections like batch1Section.batch1Size)
    path_parts = element_path.split(".")
    elements = target_step.get("elements", [])

    current = None
    for part in path_parts:
        current = _find_element_by_name(elements, part)
        if current is None:
            return None
        # If this is a Section, continue searching in its elements
        if current.get("type") == "Microsoft.Common.Section":
            elements = current.get("elements", [])
        else:
            break

    return current


def _apply_output_patches(
    ui_def: dict, output_patches: list[dict]
) -> tuple[dict, list[str]]:
    """Apply patches to the outputs.parameters section of the UI definition.

    This updates literal values in the outputs block (e.g., subnets,
    vnetAddressPrefix) that are not bound to any UI element.

    Args:
        ui_def: The UI definition dict to modify (modified in place).
        output_patches: List of patch objects with parameter_name and value.

    Returns:
        Tuple of (modified ui_def, list of status messages).
    """
    results: list[str] = []
    outputs = ui_def.get("view", {}).get("outputs", {}).get("parameters", {})

    if not outputs:
        # Try legacy path: parameters.outputs
        outputs = ui_def.get("parameters", {}).get("outputs", {})

    if not outputs:
        for patch in output_patches:
            param = patch.get("parameter_name", "unknown")
            results.append(f"NOT_FOUND: outputs.parameters (cannot patch {param})")
        return ui_def, results

    for patch in output_patches:
        param_name = patch.get("parameter_name")
        value = patch.get("value")

        if not param_name:
            results.append("SKIP: Missing parameter_name in output patch")
            continue

        if param_name in outputs:
            outputs[param_name] = value
            results.append(f"OK: outputs.parameters.{param_name}")
        else:
            # Parameter doesn't exist yet — add it
            outputs[param_name] = value
            results.append(f"OK_ADDED: outputs.parameters.{param_name}")

    return ui_def, results


def _apply_patches(ui_def: dict, patches: list[dict]) -> tuple[dict, list[str]]:
    """Apply a list of patches to the UI definition.

    Args:
        ui_def: The UI definition dict to modify (modified in place).
        patches: List of patch objects with step_name, element_path, property, value.

    Returns:
        Tuple of (modified ui_def, list of status messages).
    """
    results = []

    for patch in patches:
        step_name = patch.get("step_name")
        element_path = patch.get("element_path")
        prop = patch.get("property", "defaultValue")
        value = patch.get("value")

        if not step_name or not element_path:
            results.append(f"SKIP: Missing step_name or element_path in patch")
            continue

        element = _find_element_in_steps(ui_def, step_name, element_path)
        if element is None:
            results.append(f"NOT_FOUND: {step_name}.{element_path}")
            continue

        # Handle nested properties like constraints.allowedValues
        if "." in prop:
            prop_parts = prop.split(".")
            target = element
            for part in prop_parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[prop_parts[-1]] = value
        else:
            element[prop] = value

        results.append(f"OK: {step_name}.{element_path}.{prop}")

    return ui_def, results


def create_server() -> Server:
    """Create and configure the UI patcher MCP server.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("ui-patcher")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="patch_ui_definition",
                description=(
                    "Patch a createUiDefinition.json file with new default values. "
                    "Applies a list of patches to update element properties like defaultValue "
                    "or constraints.allowedValues. Returns the patched JSON content."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source_path": {
                            "type": "string",
                            "description": "Path to source createUiDefinition.json (default: createUiDefinition.json)",
                            "default": "createUiDefinition.json",
                        },
                        "patches": {
                            "type": "array",
                            "description": "List of patches to apply to UI step elements",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "step_name": {
                                        "type": "string",
                                        "description": "Step name (e.g., 'networking', 'compute', 'basics')",
                                    },
                                    "element_path": {
                                        "type": "string",
                                        "description": "Dot-separated path to element (e.g., 'batch1Section.batch1Size' or 'loadBalancerSubnetIndex')",
                                    },
                                    "property": {
                                        "type": "string",
                                        "description": "Property to update (default: 'defaultValue'). Use dot notation for nested props like 'constraints.allowedValues'",
                                        "default": "defaultValue",
                                    },
                                    "value": {
                                        "description": "New value for the property (string, number, array, or object)",
                                    },
                                },
                                "required": ["step_name", "element_path", "value"],
                            },
                        },
                        "output_patches": {
                            "type": "array",
                            "description": (
                                "List of patches to apply to the outputs.parameters section. "
                                "Use this for values like subnets and vnetAddressPrefix that are "
                                "literal values in outputs, not bound to UI elements."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "parameter_name": {
                                        "type": "string",
                                        "description": (
                                            "Name of the output parameter to update "
                                            "(e.g., 'subnets', 'vnetAddressPrefix')"
                                        ),
                                    },
                                    "value": {
                                        "description": "New value for the output parameter",
                                    },
                                },
                                "required": ["parameter_name", "value"],
                            },
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Path to write patched file (optional - returns content if not specified)",
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="read_ui_element",
                description=(
                    "Read a specific element from createUiDefinition.json. "
                    "Useful for inspecting current values before patching."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source_path": {
                            "type": "string",
                            "description": "Path to createUiDefinition.json (default: createUiDefinition.json)",
                            "default": "createUiDefinition.json",
                        },
                        "step_name": {
                            "type": "string",
                            "description": "Step name (e.g., 'networking', 'compute')",
                        },
                        "element_path": {
                            "type": "string",
                            "description": "Dot-separated path to element",
                        },
                    },
                    "required": ["step_name", "element_path"],
                },
            ),
            Tool(
                name="list_ui_steps",
                description=(
                    "List all steps and their elements in a createUiDefinition.json file. "
                    "Useful for discovering element names and structure."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source_path": {
                            "type": "string",
                            "description": "Path to createUiDefinition.json (default: createUiDefinition.json)",
                            "default": "createUiDefinition.json",
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool invocations."""
        if name == "patch_ui_definition":
            return await _patch_ui_definition(arguments)
        if name == "read_ui_element":
            return await _read_ui_element(arguments)
        if name == "list_ui_steps":
            return await _list_ui_steps(arguments)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


async def _patch_ui_definition(arguments: dict[str, Any]) -> list[TextContent]:
    """Apply patches to a UI definition file.

    Args:
        arguments: Tool arguments containing patches and optional paths.

    Returns:
        List with patched content or status as TextContent.
    """
    source_path = _resolve_path(arguments.get("source_path", "createUiDefinition.json"))
    patches = arguments.get("patches", [])
    output_patches = arguments.get("output_patches", [])
    output_path = arguments.get("output_path")

    if not source_path.exists():
        return [TextContent(type="text", text=f"Error: Source file not found: {source_path}")]

    if not patches and not output_patches:
        return [TextContent(type="text", text="Error: No patches or output_patches provided")]

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            ui_def = json.load(f)

        # Apply element patches
        element_results: list[str] = []
        if patches:
            ui_def, element_results = _apply_patches(ui_def, patches)

        # Apply output parameter patches
        output_results: list[str] = []
        if output_patches:
            ui_def, output_results = _apply_output_patches(ui_def, output_patches)

        all_results = element_results + output_results

        # Build output
        output_lines = [
            "# UI Definition Patch Results",
            "",
            f"**Source**: {source_path.name}",
            f"**Element Patches Applied**: {len([r for r in element_results if r.startswith('OK')])}",
            f"**Output Patches Applied**: {len([r for r in output_results if r.startswith('OK')])}",
            f"**Patches Failed**: {len([r for r in all_results if not r.startswith('OK')])}",
            "",
            "## Patch Details",
            "",
        ]
        for result in all_results:
            status = "✅" if result.startswith("OK") else "❌"
            output_lines.append(f"- {status} {result}")

        # Write or return content
        if output_path:
            out_path = _resolve_path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(ui_def, f, indent=2)
            output_lines.extend([
                "",
                f"**Output written to**: {out_path}",
            ])
        else:
            output_lines.extend([
                "",
                "## Patched JSON",
                "",
                "```json",
                json.dumps(ui_def, indent=2)[:10000],  # Truncate for large files
                "```",
                "",
                "(Content truncated if > 10KB. Use output_path to write full file.)",
            ])

        return [TextContent(type="text", text="\n".join(output_lines))]

    except json.JSONDecodeError as e:
        return [TextContent(type="text", text=f"JSON parse error: {e}")]
    except Exception as e:
        logger.exception("Unexpected error patching UI definition")
        return [TextContent(type="text", text=f"Unexpected error: {e}")]


async def _read_ui_element(arguments: dict[str, Any]) -> list[TextContent]:
    """Read a specific element from the UI definition.

    Args:
        arguments: Tool arguments containing path info.

    Returns:
        List with element content as TextContent.
    """
    source_path = _resolve_path(arguments.get("source_path", "createUiDefinition.json"))
    step_name = arguments.get("step_name")
    element_path = arguments.get("element_path")

    if not source_path.exists():
        return [TextContent(type="text", text=f"Error: File not found: {source_path}")]

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            ui_def = json.load(f)

        element = _find_element_in_steps(ui_def, step_name, element_path)

        if element is None:
            return [TextContent(type="text", text=f"Element not found: {step_name}.{element_path}")]

        output = [
            f"# Element: {step_name}.{element_path}",
            "",
            "```json",
            json.dumps(element, indent=2),
            "```",
        ]

        return [TextContent(type="text", text="\n".join(output))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _list_ui_steps(arguments: dict[str, Any]) -> list[TextContent]:
    """List all steps and elements in the UI definition.

    Args:
        arguments: Tool arguments containing optional source_path.

    Returns:
        List with structure overview as TextContent.
    """
    source_path = _resolve_path(arguments.get("source_path", "createUiDefinition.json"))

    if not source_path.exists():
        return [TextContent(type="text", text=f"Error: File not found: {source_path}")]

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            ui_def = json.load(f)

        steps = ui_def.get("view", {}).get("properties", {}).get("steps", [])

        output_lines = [
            "# UI Definition Structure",
            "",
            f"**File**: {source_path.name}",
            f"**Steps**: {len(steps)}",
            "",
        ]

        def format_elements(elements: list, indent: int = 0) -> list[str]:
            lines = []
            prefix = "  " * indent
            for elem in elements:
                name = elem.get("name", "unnamed")
                elem_type = elem.get("type", "unknown").split(".")[-1]
                default = elem.get("defaultValue", "")
                if default and isinstance(default, str) and len(default) > 30:
                    default = default[:30] + "..."
                lines.append(f"{prefix}- `{name}` ({elem_type}){f' = {default}' if default else ''}")
                # Recurse into sections
                if elem.get("type") == "Microsoft.Common.Section":
                    lines.extend(format_elements(elem.get("elements", []), indent + 1))
            return lines

        for step in steps:
            step_name = step.get("name", "unnamed")
            step_label = step.get("label", step_name)
            elements = step.get("elements", [])

            output_lines.extend([
                f"## Step: {step_name} ({step_label})",
                "",
            ])
            output_lines.extend(format_elements(elements))
            output_lines.append("")

        return [TextContent(type="text", text="\n".join(output_lines))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def main() -> None:
    """Run the UI patcher MCP server."""
    logging.basicConfig(level=logging.INFO)
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
