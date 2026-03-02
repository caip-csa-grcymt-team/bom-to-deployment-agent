"""Tests for the AVM resolver MCP server.

Tests cover the deterministic ARM-to-AVM path conversion algorithm
and the module resolution flow with mocked HTTP calls.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_servers.avm_resolver_server import AvmModuleResolver


@pytest.fixture
def resolver() -> AvmModuleResolver:
    """Create a fresh AvmModuleResolver instance."""
    return AvmModuleResolver()


class TestArmTypeToAvmPath:
    """Tests for the deterministic ARM type to AVM path conversion."""

    def test_arm_type_to_avm_path_standard(self, resolver: AvmModuleResolver) -> None:
        """Standard conversion: Microsoft.Storage/storageAccounts."""
        result = resolver._arm_type_to_avm_path("Microsoft.Storage/storageAccounts")
        assert result == "avm/res/storage/storage-account"

    def test_arm_type_to_avm_path_two_word_provider(self, resolver: AvmModuleResolver) -> None:
        """Two-word provider: Microsoft.ContainerService/managedClusters."""
        result = resolver._arm_type_to_avm_path("Microsoft.ContainerService/managedClusters")
        assert result == "avm/res/container-service/managed-cluster"

    def test_arm_type_to_avm_path_documentdb(self, resolver: AvmModuleResolver) -> None:
        """Acronym in provider: Microsoft.DocumentDB/databaseAccounts."""
        result = resolver._arm_type_to_avm_path("Microsoft.DocumentDB/databaseAccounts")
        assert result == "avm/res/document-db/database-account"

    def test_arm_type_to_avm_path_plural_ies(self, resolver: AvmModuleResolver) -> None:
        """Plural -ies suffix: Microsoft.ContainerRegistry/registries."""
        result = resolver._arm_type_to_avm_path("Microsoft.ContainerRegistry/registries")
        assert result == "avm/res/container-registry/registry"

    def test_arm_type_to_avm_path_no_double_strip(self, resolver: AvmModuleResolver) -> None:
        """No false singularization: Microsoft.Cache/redis stays redis (not redi).

        The trailing 's' in 'redis' ends with 'is', which is excluded from
        singularization to avoid stripping non-plural suffixes.
        """
        result = resolver._arm_type_to_avm_path("Microsoft.Cache/redis")
        assert result == "avm/res/cache/redis"


class TestResolveModule:
    """Tests for the full module resolution flow with mocked HTTP."""

    def test_resolve_module_with_mock_csv(self, resolver: AvmModuleResolver) -> None:
        """Test full resolution with mocked CSV and MCR tag responses."""
        csv_content = (
            "ModuleName,PrimaryResourceType,ModuleStatus,ModulePath\n"
            "storage-account,Microsoft.Storage/storageAccounts,Available,"
            "avm/res/storage/storage-account\n"
        )
        tags_response = {
            "name": "bicep/avm/res/storage/storage-account",
            "tags": ["0.9.0", "0.10.0", "0.11.0"],
        }

        async def _run() -> None:
            async def mock_get(url: str) -> MagicMock:
                resp = MagicMock()
                resp.raise_for_status = MagicMock()
                if "aka.ms" in url:
                    resp.text = csv_content
                else:
                    resp.json.return_value = tags_response
                return resp

            mock_client = AsyncMock()
            mock_client.get = mock_get

            with patch("mcp_servers.avm_resolver_server.httpx.AsyncClient") as mock_cls:
                ctx = AsyncMock()
                ctx.__aenter__.return_value = mock_client
                mock_cls.return_value = ctx

                result = await resolver.resolve("Microsoft.Storage/storageAccounts")

            assert result["path"] == "avm/res/storage/storage-account"
            assert result["version"] == "0.11.0"
            assert result["reference"] == "br/public:avm/res/storage/storage-account:0.11.0"
            assert result["status"] == "Available"

        asyncio.run(_run())

    def test_resolve_module_network_failure(self, resolver: AvmModuleResolver) -> None:
        """Test graceful degradation when network is unavailable."""

        async def _run() -> None:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Network unreachable"))

            with patch("mcp_servers.avm_resolver_server.httpx.AsyncClient") as mock_cls:
                ctx = AsyncMock()
                ctx.__aenter__.return_value = mock_client
                mock_cls.return_value = ctx

                result = await resolver.resolve("Microsoft.Storage/storageAccounts")

            assert result["path"] == "avm/res/storage/storage-account"
            assert result["version"] == "latest"
            assert result["reference"] == "br/public:avm/res/storage/storage-account:latest"
            assert result["status"] == "unverified"

        asyncio.run(_run())
