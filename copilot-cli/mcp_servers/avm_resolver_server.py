"""MCP server for resolving Azure Verified Module (AVM) references.

Provides dynamic AVM module resolution by mapping ARM resource types
to AVM Bicep module references using the AVM CSV index and Microsoft
Container Registry (MCR) tags API.

Environment Variables:
    None required — uses public AVM index and MCR endpoints.

Example:
    Start the server with:
        python -m mcp_servers.avm_resolver_server

    Or use with Copilot CLI via mcp-config.json.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import time
from io import StringIO
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

AVM_CSV_URL = "https://aka.ms/avm/index/bicep/res/csv"
MCR_BASE_URL = "https://mcr.microsoft.com"
CSV_CACHE_TTL = 86400  # 24 hours in seconds
VERSION_CACHE_TTL = 3600  # 1 hour in seconds


class AvmModuleResolver:
    """Resolves ARM resource types to Azure Verified Module (AVM) Bicep references.

    Uses a three-phase resolution strategy:
    1. Deterministic path mapping from ARM type to AVM module path
    2. CSV index validation against the official AVM module index
    3. MCR version resolution to find the latest published version
    """

    def __init__(self) -> None:
        """Initialize resolver with empty caches."""
        self._csv_cache: dict[str, dict] | None = None
        self._csv_cache_time: float = 0
        self._version_cache: dict[str, tuple[str, float]] = {}

    async def _load_csv_index(self) -> dict[str, dict]:
        """Download and parse the AVM Bicep resource modules CSV index.

        Builds a lookup dict keyed by ARM resource type
        (e.g. ``Microsoft.Storage/storageAccounts``). Results are cached for
        24 hours.

        Returns:
            Dict mapping ARM resource types to their CSV row data.
        """
        now = time.monotonic()
        if self._csv_cache is not None and (now - self._csv_cache_time) < CSV_CACHE_TTL:
            return self._csv_cache

        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(AVM_CSV_URL)
            resp.raise_for_status()

        reader = csv.DictReader(StringIO(resp.text))
        index: dict[str, dict] = {}

        for row in reader:
            # Try known column names for the ARM resource type
            arm_type = row.get("PrimaryResourceType", "")
            if not arm_type:
                provider = row.get("ProviderNamespace", "")
                resource = row.get("ResourceType", "")
                if provider and resource:
                    arm_type = f"{provider}/{resource}"
            if arm_type:
                index[arm_type] = dict(row)

        self._csv_cache = index
        self._csv_cache_time = now
        return index

    def _arm_type_to_avm_path(self, arm_type: str) -> str:
        """Convert an ARM resource type to an AVM module path deterministically.

        Algorithm:
        1. Split on ``/``, extract provider (remove ``Microsoft.`` prefix) and
           resource type.
        2. Convert CamelCase to kebab-case.
        3. Singularize the resource type.
        4. Return ``avm/res/{provider_kebab}/{resource_kebab}``.

        Args:
            arm_type: ARM resource type (e.g. ``Microsoft.Storage/storageAccounts``).

        Returns:
            AVM module path (e.g. ``avm/res/storage/storage-account``).

        Raises:
            ValueError: If the ARM type format is invalid.
        """
        parts = arm_type.split("/")
        if len(parts) != 2:
            msg = f"Invalid ARM type format '{arm_type}': expected 'Microsoft.Provider/resourceType'"
            raise ValueError(msg)

        provider_raw = parts[0]
        resource_type = parts[1]

        # Remove Microsoft. prefix
        if provider_raw.startswith("Microsoft."):
            provider_raw = provider_raw[len("Microsoft.") :]

        # CamelCase to kebab-case via regex: insert hyphen before uppercase
        # letters that follow a lowercase letter or digit
        provider_kebab = re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", provider_raw).lower()
        resource_kebab = re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", resource_type).lower()

        # Singularize resource type
        resource_kebab = self._singularize(resource_kebab)

        return f"avm/res/{provider_kebab}/{resource_kebab}"

    @staticmethod
    def _singularize(word: str) -> str:
        """Apply simple English singularization rules to a kebab-case word.

        Rules applied in order:

        - Trailing ``ies`` → ``y`` (e.g. ``registries`` → ``registry``).
        - Trailing ``s`` removed unless the word ends in ``ss`` or ``is``
          (e.g. ``accounts`` → ``account``, but ``redis`` stays ``redis``).

        Args:
            word: Kebab-case word to singularize.

        Returns:
            Singularized word.
        """
        if word.endswith("ies"):
            return word[:-3] + "y"
        if word.endswith("s") and not word.endswith("ss") and not word.endswith("is"):
            return word[:-1]
        return word

    async def _resolve_latest_version(self, module_path: str) -> str:
        """Resolve the latest version tag from MCR for an AVM module.

        Queries the Microsoft Container Registry tags API and returns the
        highest semantic version tag. Results are cached for 1 hour.

        Args:
            module_path: AVM module path (e.g. ``avm/res/storage/storage-account``).

        Returns:
            Latest semver tag string (e.g. ``0.11.0``).

        Raises:
            httpx.HTTPStatusError: If the MCR API returns an error status.
            ValueError: If no tags are found for the module.
        """
        now = time.monotonic()
        cached = self._version_cache.get(module_path)
        if cached and (now - cached[1]) < VERSION_CACHE_TTL:
            return cached[0]

        url = f"{MCR_BASE_URL}/v2/bicep/{module_path}/tags/list"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        data = resp.json()
        tags = data.get("tags", [])
        if not tags:
            msg = f"No tags found for module: {module_path}"
            raise ValueError(msg)

        def _semver_key(tag: str) -> tuple[int, ...]:
            """Parse a semver tag into a comparable tuple."""
            try:
                return tuple(int(x) for x in tag.split("."))
            except ValueError:
                return (0,)

        latest = max(tags, key=_semver_key)
        self._version_cache[module_path] = (latest, now)
        return latest

    async def resolve(self, arm_type: str) -> dict[str, Any]:
        """Resolve an ARM resource type to a full AVM module reference.

        Three-phase resolution:

        1. Deterministic path mapping
        2. CSV index validation (confirm module exists, get status)
        3. MCR version resolution (find latest published tag)

        Args:
            arm_type: ARM resource type (e.g. ``Microsoft.Storage/storageAccounts``).

        Returns:
            Dict with keys ``path``, ``version``, ``reference``, ``status``.
            On error: ``path=None``, ``status='error'|'not_found'``, ``message=str``.
        """
        # Validate ARM type format
        if "/" not in arm_type or not arm_type.startswith("Microsoft."):
            return {
                "path": None,
                "status": "error",
                "message": f"Invalid ARM type format '{arm_type}': expected 'Microsoft.Provider/resourceType'",
            }

        # Phase 1: Deterministic path mapping
        try:
            module_path = self._arm_type_to_avm_path(arm_type)
        except ValueError as e:
            return {"path": None, "status": "error", "message": str(e)}

        # Phase 2: CSV index validation
        csv_status = "unverified"
        try:
            index = await self._load_csv_index()
            csv_entry = index.get(arm_type)
            if csv_entry:
                csv_status = csv_entry.get("ModuleStatus", csv_entry.get("Status", "available"))
            else:
                csv_status = "not_in_index"
        except Exception:
            logger.warning("Failed to load AVM CSV index for %s", arm_type, exc_info=True)
            csv_status = "unverified"

        # Phase 3: MCR version resolution
        try:
            version = await self._resolve_latest_version(module_path)
            return {
                "path": module_path,
                "version": version,
                "reference": f"br/public:{module_path}:{version}",
                "status": csv_status if csv_status != "not_in_index" else "available",
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {
                    "path": None,
                    "status": "not_found",
                    "message": f"No AVM module found at '{module_path}' for ARM type '{arm_type}'",
                }
            logger.warning("MCR API error for %s: %s", module_path, e)
            return {
                "path": module_path,
                "version": "latest",
                "reference": f"br/public:{module_path}:latest",
                "status": "unverified",
            }
        except Exception:
            logger.warning("Failed to resolve version for %s", module_path, exc_info=True)
            return {
                "path": module_path,
                "version": "latest",
                "reference": f"br/public:{module_path}:latest",
                "status": "unverified",
            }

    async def list_modules(self) -> list[dict[str, str]]:
        """Return all modules from the AVM CSV index.

        Returns:
            List of dicts with ``arm_type``, ``module_name``, ``module_path``,
            and ``status`` keys.
        """
        try:
            index = await self._load_csv_index()
            return [
                {
                    "arm_type": key,
                    "module_name": entry.get("ModuleName", ""),
                    "module_path": entry.get("ModulePath", ""),
                    "status": entry.get("ModuleStatus", entry.get("Status", "unknown")),
                }
                for key, entry in index.items()
            ]
        except Exception as e:
            logger.warning("Failed to load AVM module index", exc_info=True)
            return [{"error": f"Failed to load module index: {e}"}]


def create_server() -> Server:
    """Create and configure the AVM resolver MCP server.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("avm-resolver")
    resolver = AvmModuleResolver()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="resolve_module",
                description=(
                    "Resolve an ARM resource type to an Azure Verified Module (AVM) Bicep reference. "
                    "Returns the module path, latest version, and full br/public reference string."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "arm_type": {
                            "type": "string",
                            "description": (
                                "ARM resource type to resolve "
                                "(e.g. 'Microsoft.Storage/storageAccounts')"
                            ),
                        },
                    },
                    "required": ["arm_type"],
                },
            ),
            Tool(
                name="list_available_modules",
                description=(
                    "List all available Azure Verified Module (AVM) Bicep resource modules "
                    "from the official index."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool invocations."""
        if name == "resolve_module":
            return await _handle_resolve_module(resolver, arguments)
        if name == "list_available_modules":
            return await _handle_list_modules(resolver)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


async def _handle_resolve_module(
    resolver: AvmModuleResolver,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Handle the resolve_module tool invocation.

    Args:
        resolver: AvmModuleResolver instance.
        arguments: Tool arguments containing arm_type.

    Returns:
        List with resolution result as JSON TextContent.
    """
    arm_type = arguments.get("arm_type")
    if not arm_type:
        return [TextContent(type="text", text=json.dumps({"error": "arm_type is required"}))]

    result = await resolver.resolve(arm_type)
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _handle_list_modules(resolver: AvmModuleResolver) -> list[TextContent]:
    """Handle the list_available_modules tool invocation.

    Args:
        resolver: AvmModuleResolver instance.

    Returns:
        List with module listing as TextContent.
    """
    modules = await resolver.list_modules()

    if modules and "error" in modules[0]:
        return [TextContent(type="text", text=f"Error: {modules[0]['error']}")]

    output_lines = [
        "# Available AVM Bicep Resource Modules",
        "",
        f"**Total modules**: {len(modules)}",
        "",
    ]

    for mod in modules[:50]:
        arm_type = mod.get("arm_type", "unknown")
        status = mod.get("status", "unknown")
        output_lines.append(f"- **{arm_type}** (Status: {status})")

    if len(modules) > 50:
        output_lines.append(f"\n... and {len(modules) - 50} more modules")

    return [TextContent(type="text", text="\n".join(output_lines))]


async def main() -> None:
    """Run the AVM resolver MCP server."""
    logging.basicConfig(level=logging.INFO)
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
