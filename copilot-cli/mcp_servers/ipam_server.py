"""MCP server for Azure IPAM operations.

Provides CIDR reservation capabilities for Azure IPAM via MCP tools
for use with GitHub Copilot CLI.

Example:
    Start the server with:
        python -m mcp_servers.ipam_server

    Required environment variables:
        IPAM_FQDN - IPAM engine FQDN (e.g., ipamdev.azurewebsites.net)
        IPAM_SPACE - IPAM space name
        IPAM_BLOCK - IPAM block name
        IPAM_ENGINE_CLIENT_ID - Azure AD Engine App Registration Client ID

    Authentication:
        Uses DefaultAzureCredential to obtain a token for the IPAM Engine API.
        Ensure you are logged in via 'az login' or have appropriate credentials.

    Or use with Copilot CLI via mcp-config.json.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 30


class IpamClientError(Exception):
    """Base error for IPAM client operations."""


class IpamAuthError(IpamClientError):
    """Raised when authentication to the IPAM API fails (HTTP 401)."""


class IpamConflictError(IpamClientError):
    """Raised when a reservation conflicts with existing allocations (HTTP 409)."""


class IpamServerError(IpamClientError):
    """Raised when the IPAM API returns a server error (HTTP 5xx)."""


def _get_required_env(name: str) -> str:
    """Get a required environment variable.

    Args:
        name: Environment variable name.

    Returns:
        Environment variable value.

    Raises:
        ValueError: If the environment variable is not set.
    """
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Required environment variable not set: {name}")
    return value


def _get_ipam_token(engine_client_id: str) -> str:
    """Obtain an Azure AD token for the IPAM Engine API.

    Uses DefaultAzureCredential which supports:
    - Azure CLI (az login)
    - Environment variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
    - Managed Identity (when running in Azure)
    - VS Code Azure extension

    Args:
        engine_client_id: The IPAM Engine App Registration Client ID.

    Returns:
        Bearer token string.

    Raises:
        IpamAuthError: If token acquisition fails.
    """
    try:
        credential = DefaultAzureCredential()
        # Token scope for IPAM API: api://{engineClientId}/.default
        scope = f"api://{engine_client_id}/.default"
        token = credential.get_token(scope)
        return token.token
    except Exception as e:
        raise IpamAuthError(f"Failed to obtain Azure AD token: {e}") from e


def _raise_for_status(response: httpx.Response, context: str) -> None:
    """Raise a typed exception for non-success HTTP responses.

    Args:
        response: The httpx Response object.
        context: Description of the operation for error messages.

    Raises:
        IpamAuthError: If HTTP 401.
        IpamConflictError: If HTTP 409.
        IpamServerError: If HTTP 5xx.
        IpamClientError: For other non-success responses.
    """
    if response.is_success:
        return

    status = response.status_code
    detail = response.text[:200] if response.text else "No details"

    if status == 401:
        raise IpamAuthError(f"Authentication failed for {context}: {detail}")
    if status == 409:
        raise IpamConflictError(f"Conflict during {context}: {detail}")
    if status >= 500:
        raise IpamServerError(f"Server error during {context}: HTTP {status} - {detail}")

    raise IpamClientError(f"Request failed for {context}: HTTP {status} - {detail}")


def reserve_cidr(
    fqdn: str,
    space: str,
    block: str,
    engine_client_id: str,
    size: int,
    description: str,
) -> dict[str, Any]:
    """Reserve a CIDR block from the IPAM pool.

    Args:
        fqdn: IPAM engine FQDN (e.g., ipamdev.azurewebsites.net).
        space: IPAM space name.
        block: IPAM block name.
        engine_client_id: Azure AD Engine App Registration Client ID.
        size: Prefix length for the reservation (e.g., 24 for a /24).
        description: Human-readable label for the reservation.

    Returns:
        Dictionary containing:
            - cidr: The reserved CIDR notation (e.g., 10.0.0.0/24)
            - id: Unique reservation identifier
            - tag: IPAM tag metadata

    Raises:
        IpamAuthError: If the token is rejected (HTTP 401).
        IpamConflictError: If the address space is exhausted (HTTP 409).
        IpamServerError: If the API returns a 5xx error.
        IpamClientError: For any other non-success response.
    """
    token = _get_ipam_token(engine_client_id)

    url = f"https://{fqdn}/api/spaces/{space}/blocks/{block}/reservations"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = {
        "size": size,
        "desc": description,
        "reverse_search": False,
        "smallest_cidr": True,
    }

    logger.info("Reserving /%d CIDR in space=%s block=%s", size, space, block)

    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SECONDS) as client:
        response = client.post(url, json=body, headers=headers)

    _raise_for_status(response, f"reserve /{size}")

    data: dict[str, Any] = response.json()
    logger.info("Reserved CIDR %s (id=%s)", data.get("cidr"), data.get("id"))
    return data


def release_reservation(
    fqdn: str,
    space: str,
    block: str,
    engine_client_id: str,
    reservation_id: str,
) -> None:
    """Release a previously reserved CIDR block.

    Args:
        fqdn: IPAM engine FQDN.
        space: IPAM space name.
        block: IPAM block name.
        engine_client_id: Azure AD Engine App Registration Client ID.
        reservation_id: The unique identifier of the reservation to release.

    Raises:
        IpamAuthError: If the token is rejected (HTTP 401).
        IpamServerError: If the API returns a 5xx error.
        IpamClientError: For any other unexpected response.
    """
    token = _get_ipam_token(engine_client_id)

    url = f"https://{fqdn}/api/spaces/{space}/blocks/{block}/reservations/{reservation_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    logger.info("Releasing reservation %s", reservation_id)

    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SECONDS) as client:
        response = client.delete(url, headers=headers)

    if response.status_code == 404:
        logger.warning("Reservation %s not found; may already be released", reservation_id)
        return

    _raise_for_status(response, f"release {reservation_id}")
    logger.info("Released reservation %s", reservation_id)


def get_reservation_status(
    fqdn: str,
    space: str,
    block: str,
    engine_client_id: str,
    reservation_id: str,
) -> dict[str, Any]:
    """Get the status of an IPAM reservation and any associated VNet.

    Args:
        fqdn: IPAM engine FQDN.
        space: IPAM space name.
        block: IPAM block name.
        engine_client_id: Azure AD Engine App Registration Client ID.
        reservation_id: The unique identifier of the reservation to check.

    Returns:
        Dictionary containing:
            - id: Reservation ID
            - cidr: Reserved CIDR block
            - status: Reservation status (wait, fulfilled, warnCIDRMismatch, errCIDRExists)
            - settledOn: Timestamp when fulfilled (if applicable)
            - settledBy: VNet resource ID (if fulfilled)

    Raises:
        IpamAuthError: If the token is rejected (HTTP 401).
        IpamServerError: If the API returns a 5xx error.
        IpamClientError: For any other non-success response.
    """
    token = _get_ipam_token(engine_client_id)

    url = f"https://{fqdn}/api/spaces/{space}/blocks/{block}/reservations"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    logger.info("Checking reservation status for %s", reservation_id)

    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SECONDS) as client:
        response = client.get(url, headers=headers)

    _raise_for_status(response, f"get reservations")

    reservations: list[dict[str, Any]] = response.json()

    # Find the specific reservation
    for res in reservations:
        if res.get("id") == reservation_id:
            logger.info(
                "Reservation %s status: %s",
                reservation_id,
                res.get("status", "unknown"),
            )
            return res

    raise IpamClientError(f"Reservation {reservation_id} not found in block {block}")


def create_server() -> Server:
    """Create and configure the IPAM MCP server.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("ipam-client")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="reserve_cidr",
                description=(
                    "Reserve a CIDR block from Azure IPAM for a new VNet. "
                    "Returns the reserved CIDR notation and reservation ID. "
                    "Requires IPAM environment variables and Azure authentication (az login)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "authority_id": {
                            "type": "string",
                            "description": "Authority/Agency identifier (e.g., 'MIN01')",
                        },
                        "project_id": {
                            "type": "string",
                            "description": "Project identifier (e.g., 'RG100')",
                        },
                        "prefix_length": {
                            "type": "integer",
                            "description": "CIDR prefix length to reserve (e.g., 24 for /24)",
                            "minimum": 16,
                            "maximum": 28,
                        },
                    },
                    "required": ["authority_id", "project_id", "prefix_length"],
                },
            ),
            Tool(
                name="release_cidr",
                description=(
                    "Release a previously reserved CIDR block. "
                    "Use this to clean up reservations that are no longer needed."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "reservation_id": {
                            "type": "string",
                            "description": "The reservation ID returned from reserve_cidr",
                        },
                    },
                    "required": ["reservation_id"],
                },
            ),
            Tool(
                name="check_ipam_config",
                description=(
                    "Check if IPAM environment variables are configured and Azure auth is available. "
                    "Returns configuration status without revealing sensitive values."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="check_association_status",
                description=(
                    "Check the status of an IPAM reservation to verify if a VNet has been associated. "
                    "Returns the reservation status (wait, fulfilled, etc.) and VNet resource ID if associated. "
                    "Use this after VNet deployment to confirm IPAM has discovered and linked the VNet."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "reservation_id": {
                            "type": "string",
                            "description": "The IPAM reservation ID to check",
                        },
                    },
                    "required": ["reservation_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool invocations."""
        if name == "reserve_cidr":
            return await _reserve_cidr_tool(arguments)
        if name == "release_cidr":
            return await _release_cidr_tool(arguments)
        if name == "check_ipam_config":
            return await _check_ipam_config()
        if name == "check_association_status":
            return await _check_association_status_tool(arguments)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


async def _reserve_cidr_tool(arguments: dict[str, Any]) -> list[TextContent]:
    """Reserve a CIDR block from IPAM.

    Args:
        arguments: Tool arguments.

    Returns:
        List with reservation result as TextContent.
    """
    authority_id = arguments.get("authority_id")
    project_id = arguments.get("project_id")
    prefix_length = arguments.get("prefix_length")

    if not all([authority_id, project_id, prefix_length]):
        return [TextContent(type="text", text="Error: authority_id, project_id, and prefix_length are required")]

    try:
        fqdn = _get_required_env("IPAM_FQDN")
        space = _get_required_env("IPAM_SPACE")
        block = _get_required_env("IPAM_BLOCK")
        engine_client_id = _get_required_env("IPAM_ENGINE_CLIENT_ID")

        description = f"{authority_id}-{project_id}"
        result = reserve_cidr(
            fqdn=fqdn,
            space=space,
            block=block,
            engine_client_id=engine_client_id,
            size=prefix_length,
            description=description,
        )

        output = [
            "# CIDR Reservation Successful",
            "",
            f"**CIDR**: `{result.get('cidr')}`",
            f"**Reservation ID**: `{result.get('id')}`",
            f"**Tag**: `{result.get('tag', 'N/A')}`",
            "",
            "Store the reservation ID for potential rollback.",
        ]

        return [TextContent(type="text", text="\n".join(output))]

    except ValueError as e:
        return [TextContent(type="text", text=f"Configuration error: {e}")]
    except IpamAuthError as e:
        return [TextContent(type="text", text=f"Authentication error: {e}\n\nEnsure you are logged in with 'az login'")]
    except IpamClientError as e:
        return [TextContent(type="text", text=f"IPAM error: {e}")]
    except Exception as e:
        logger.exception("Unexpected error reserving CIDR")
        return [TextContent(type="text", text=f"Unexpected error: {e}")]


async def _release_cidr_tool(arguments: dict[str, Any]) -> list[TextContent]:
    """Release a CIDR reservation.

    Args:
        arguments: Tool arguments containing reservation_id.

    Returns:
        List with release result as TextContent.
    """
    reservation_id = arguments.get("reservation_id")
    if not reservation_id:
        return [TextContent(type="text", text="Error: reservation_id is required")]

    try:
        fqdn = _get_required_env("IPAM_FQDN")
        space = _get_required_env("IPAM_SPACE")
        block = _get_required_env("IPAM_BLOCK")
        engine_client_id = _get_required_env("IPAM_ENGINE_CLIENT_ID")

        release_reservation(
            fqdn=fqdn,
            space=space,
            block=block,
            engine_client_id=engine_client_id,
            reservation_id=reservation_id,
        )

        return [TextContent(type="text", text=f"Successfully released reservation: {reservation_id}")]

    except ValueError as e:
        return [TextContent(type="text", text=f"Configuration error: {e}")]
    except IpamAuthError as e:
        return [TextContent(type="text", text=f"Authentication error: {e}\n\nEnsure you are logged in with 'az login'")]
    except IpamClientError as e:
        return [TextContent(type="text", text=f"IPAM error: {e}")]
    except Exception as e:
        logger.exception("Unexpected error releasing CIDR")
        return [TextContent(type="text", text=f"Unexpected error: {e}")]


async def _check_ipam_config() -> list[TextContent]:
    """Check IPAM environment configuration and Azure auth.

    Returns:
        List with configuration status as TextContent.
    """
    required_vars = ["IPAM_FQDN", "IPAM_SPACE", "IPAM_BLOCK", "IPAM_ENGINE_CLIENT_ID"]
    status = []

    for var in required_vars:
        is_set = bool(os.environ.get(var))
        icon = "✅" if is_set else "❌"
        status.append(f"{icon} `{var}`: {'Set' if is_set else 'Not set'}")

    all_env_set = all(os.environ.get(var) for var in required_vars)

    # Check Azure authentication
    auth_status = "❌ Not authenticated"
    if all_env_set:
        try:
            engine_client_id = os.environ.get("IPAM_ENGINE_CLIENT_ID", "")
            _get_ipam_token(engine_client_id)
            auth_status = "✅ Authenticated (token acquired successfully)"
        except IpamAuthError as e:
            auth_status = f"❌ Authentication failed: {e}"
        except Exception as e:
            auth_status = f"❌ Auth check error: {e}"

    output = [
        "# IPAM Configuration Status",
        "",
        "## Environment Variables",
        *status,
        "",
        "## Azure Authentication",
        auth_status,
        "",
        f"**Ready**: {'Yes' if all_env_set and '✅' in auth_status else 'No'}",
        "",
        "If not authenticated, run `az login` to authenticate.",
    ]

    return [TextContent(type="text", text="\n".join(output))]


async def _check_association_status_tool(arguments: dict[str, Any]) -> list[TextContent]:
    """Check the association status of an IPAM reservation.

    Args:
        arguments: Tool arguments containing reservation_id.

    Returns:
        List with association status as TextContent.
    """
    reservation_id = arguments.get("reservation_id")
    if not reservation_id:
        return [TextContent(type="text", text="Error: reservation_id is required")]

    try:
        fqdn = _get_required_env("IPAM_FQDN")
        space = _get_required_env("IPAM_SPACE")
        block = _get_required_env("IPAM_BLOCK")
        engine_client_id = _get_required_env("IPAM_ENGINE_CLIENT_ID")

        result = get_reservation_status(
            fqdn=fqdn,
            space=space,
            block=block,
            engine_client_id=engine_client_id,
            reservation_id=reservation_id,
        )

        status = result.get("status", "unknown")
        cidr = result.get("cidr", "N/A")
        settled_by = result.get("settledBy", "")
        settled_on = result.get("settledOn", "")

        # Determine status icon and message
        if status == "fulfilled":
            status_icon = "✅"
            status_msg = "VNet successfully associated"
        elif status == "wait":
            status_icon = "⏳"
            status_msg = "Waiting for VNet association (IPAM background job runs every ~60 sec)"
        elif status == "warnCIDRMismatch":
            status_icon = "⚠️"
            status_msg = "Warning: VNet found but CIDR does not match reservation"
        elif status == "errCIDRExists":
            status_icon = "❌"
            status_msg = "Error: A VNet with this CIDR already exists"
        else:
            status_icon = "❓"
            status_msg = f"Unknown status: {status}"

        output = [
            "# IPAM Reservation Association Status",
            "",
            f"**Reservation ID**: `{reservation_id}`",
            f"**CIDR**: `{cidr}`",
            f"**Status**: {status_icon} {status}",
            f"**Message**: {status_msg}",
        ]

        if settled_by:
            output.append(f"**VNet Resource ID**: `{settled_by}`")
        if settled_on:
            output.append(f"**Associated On**: {settled_on}")

        return [TextContent(type="text", text="\n".join(output))]

    except ValueError as e:
        return [TextContent(type="text", text=f"Configuration error: {e}")]
    except IpamAuthError as e:
        return [TextContent(type="text", text=f"Authentication error: {e}\n\nEnsure you are logged in with 'az login'")]
    except IpamClientError as e:
        return [TextContent(type="text", text=f"IPAM error: {e}")]
    except Exception as e:
        logger.exception("Unexpected error checking association status")
        return [TextContent(type="text", text=f"Unexpected error: {e}")]


async def main() -> None:
    """Run the IPAM MCP server."""
    logging.basicConfig(level=logging.INFO)
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
