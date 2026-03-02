"""Tests for the ui-patcher MCP server.

These tests verify the JSON patching functionality for createUiDefinition.json files.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from mcp_servers.ui_patcher_server import (
    _apply_output_patches,
    _apply_patches,
    _find_element_in_steps,
    _resolve_path,
)


@pytest.fixture
def sample_ui_definition() -> dict:
    """Create a sample createUiDefinition.json structure for testing."""
    return {
        "view": {
            "properties": {
                "steps": [
                    {
                        "name": "basics",
                        "label": "Basics",
                        "elements": [
                            {
                                "name": "agency",
                                "type": "Microsoft.Common.TextBox",
                                "label": "Agency",
                                "defaultValue": "",
                            },
                            {
                                "name": "project",
                                "type": "Microsoft.Common.TextBox",
                                "label": "Project",
                                "defaultValue": "",
                            },
                        ],
                    },
                    {
                        "name": "networking",
                        "label": "Networking",
                        "elements": [
                            {
                                "name": "vnetAddressSpace",
                                "type": "Microsoft.Common.TextBox",
                                "label": "VNet Address Space",
                                "defaultValue": "10.0.0.0/22",
                            },
                        ],
                    },
                    {
                        "name": "compute",
                        "label": "Compute",
                        "elements": [
                            {
                                "name": "batch1Section",
                                "type": "Microsoft.Common.Section",
                                "label": "VM Batch 1",
                                "elements": [
                                    {
                                        "name": "batch1Size",
                                        "type": "Microsoft.Common.DropDown",
                                        "label": "VM Size",
                                        "defaultValue": "Standard D2s v5",
                                        "constraints": {
                                            "allowedValues": [
                                                {"label": "Standard D2s v5", "value": "Standard_D2s_v5"},
                                                {"label": "Standard D4s v5", "value": "Standard_D4s_v5"},
                                            ],
                                        },
                                    },
                                    {
                                        "name": "batch1Subnet",
                                        "type": "Microsoft.Common.DropDown",
                                        "label": "Subnet",
                                        "defaultValue": "",
                                        "constraints": {
                                            "allowedValues": [],
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
            "outputs": {
                "parameters": {
                    "vnetAddressPrefix": ["10.0.0.0/24"],
                    "useExistingVnet": True,
                    "subnets": [{"addressPrefix": "10.0.0.0/26", "usage": "VM/PrivateEndpoint"}],
                },
            },
        },
    }


class TestFindElementInSteps:
    """Tests for the _find_element_in_steps function."""

    def test_find_top_level_element(self, sample_ui_definition: dict) -> None:
        """Test finding a top-level element within a step."""
        element = _find_element_in_steps(sample_ui_definition, "basics", "agency")
        assert element is not None
        assert element["name"] == "agency"
        assert element["type"] == "Microsoft.Common.TextBox"

    def test_find_nested_section_element(self, sample_ui_definition: dict) -> None:
        """Test finding an element nested within a section."""
        element = _find_element_in_steps(
            sample_ui_definition, "compute", "batch1Section.batch1Size"
        )
        assert element is not None
        assert element["name"] == "batch1Size"
        assert element["type"] == "Microsoft.Common.DropDown"

    def test_find_nonexistent_step(self, sample_ui_definition: dict) -> None:
        """Test that finding an element in a nonexistent step returns None."""
        element = _find_element_in_steps(
            sample_ui_definition, "nonexistent", "agency"
        )
        assert element is None

    def test_find_nonexistent_element(self, sample_ui_definition: dict) -> None:
        """Test that finding a nonexistent element returns None."""
        element = _find_element_in_steps(
            sample_ui_definition, "basics", "nonexistent"
        )
        assert element is None


class TestApplyPatches:
    """Tests for the _apply_patches function."""

    def test_patch_simple_default_value(self, sample_ui_definition: dict) -> None:
        """Test patching a simple defaultValue property."""
        patches = [
            {
                "step_name": "basics",
                "element_path": "agency",
                "value": "MIN69",
            },
        ]
        patched, results = _apply_patches(sample_ui_definition, patches)

        assert "OK: basics.agency.defaultValue" in results
        element = _find_element_in_steps(patched, "basics", "agency")
        assert element["defaultValue"] == "MIN69"

    def test_patch_nested_section_element(self, sample_ui_definition: dict) -> None:
        """Test patching an element inside a section."""
        patches = [
            {
                "step_name": "compute",
                "element_path": "batch1Section.batch1Size",
                "value": "Standard D4s v5",
            },
        ]
        patched, results = _apply_patches(sample_ui_definition, patches)

        assert "OK: compute.batch1Section.batch1Size.defaultValue" in results
        element = _find_element_in_steps(
            patched, "compute", "batch1Section.batch1Size"
        )
        assert element["defaultValue"] == "Standard D4s v5"

    def test_patch_nested_property(self, sample_ui_definition: dict) -> None:
        """Test patching a nested property like constraints.allowedValues."""
        new_allowed_values = [
            {"label": "snet-vm-01 (10.0.0.32/26)", "value": "1"},
            {"label": "snet-vm-02 (10.0.0.96/26)", "value": "2"},
        ]
        patches = [
            {
                "step_name": "compute",
                "element_path": "batch1Section.batch1Subnet",
                "property": "constraints.allowedValues",
                "value": new_allowed_values,
            },
        ]
        patched, results = _apply_patches(sample_ui_definition, patches)

        assert "OK: compute.batch1Section.batch1Subnet.constraints.allowedValues" in results
        element = _find_element_in_steps(
            patched, "compute", "batch1Section.batch1Subnet"
        )
        assert element["constraints"]["allowedValues"] == new_allowed_values

    def test_patch_multiple_fields(self, sample_ui_definition: dict) -> None:
        """Test patching multiple fields at once."""
        patches = [
            {"step_name": "basics", "element_path": "agency", "value": "MIN69"},
            {"step_name": "basics", "element_path": "project", "value": "RG169"},
            {
                "step_name": "networking",
                "element_path": "vnetAddressSpace",
                "value": "10.1.0.0/22",
            },
        ]
        patched, results = _apply_patches(sample_ui_definition, patches)

        ok_results = [r for r in results if r.startswith("OK")]
        assert len(ok_results) == 3

    def test_patch_nonexistent_element_fails(self, sample_ui_definition: dict) -> None:
        """Test that patching a nonexistent element reports NOT_FOUND."""
        patches = [
            {"step_name": "basics", "element_path": "nonexistent", "value": "test"},
        ]
        _, results = _apply_patches(sample_ui_definition, patches)

        assert "NOT_FOUND: basics.nonexistent" in results

    def test_patch_missing_step_name_skipped(self, sample_ui_definition: dict) -> None:
        """Test that patches without step_name are skipped."""
        patches = [
            {"element_path": "agency", "value": "test"},
        ]
        _, results = _apply_patches(sample_ui_definition, patches)

        assert any("SKIP" in r for r in results)


class TestResolvePath:
    """Tests for the _resolve_path function."""

    def test_absolute_path_unchanged(self) -> None:
        """Test that absolute paths are returned as-is."""
        # Windows paths
        abs_path = "C:\\Users\\test\\file.json"
        result = _resolve_path(abs_path)
        assert result.is_absolute()

    def test_relative_path_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that relative paths are resolved against workspace root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("WORKSPACE_ROOT", tmpdir)
            result = _resolve_path("output/test.json")
            # Normalize both paths to handle Windows short path names (e.g., VZISIA~1)
            assert result.parent.name == "output"
            assert result.name == "test.json"


class TestApplyOutputPatches:
    """Tests for the _apply_output_patches function."""

    def test_patch_subnets_in_outputs(self, sample_ui_definition: dict) -> None:
        """Test patching the subnets array in the outputs section."""
        new_subnets = [
            {"addressPrefix": "10.2.5.64/27", "usage": "AppGateway"},
            {"addressPrefix": "10.2.5.96/27", "usage": "VM/PrivateEndpoint"},
        ]
        output_patches = [
            {"parameter_name": "subnets", "value": new_subnets},
        ]
        patched, results = _apply_output_patches(sample_ui_definition, output_patches)

        assert "OK: outputs.parameters.subnets" in results
        assert patched["view"]["outputs"]["parameters"]["subnets"] == new_subnets

    def test_patch_vnet_address_prefix_in_outputs(self, sample_ui_definition: dict) -> None:
        """Test patching vnetAddressPrefix in the outputs section."""
        output_patches = [
            {"parameter_name": "vnetAddressPrefix", "value": ["10.2.5.64/26"]},
        ]
        patched, results = _apply_output_patches(sample_ui_definition, output_patches)

        assert "OK: outputs.parameters.vnetAddressPrefix" in results
        assert patched["view"]["outputs"]["parameters"]["vnetAddressPrefix"] == ["10.2.5.64/26"]

    def test_patch_multiple_output_params(self, sample_ui_definition: dict) -> None:
        """Test patching multiple output parameters at once."""
        new_subnets = [
            {"addressPrefix": "10.2.5.64/27", "usage": "AppGateway"},
            {"addressPrefix": "10.2.5.96/27", "usage": "VM/PrivateEndpoint"},
        ]
        output_patches = [
            {"parameter_name": "subnets", "value": new_subnets},
            {"parameter_name": "vnetAddressPrefix", "value": ["10.2.5.64/26"]},
            {"parameter_name": "useExistingVnet", "value": True},
        ]
        patched, results = _apply_output_patches(sample_ui_definition, output_patches)

        ok_results = [r for r in results if r.startswith("OK")]
        assert len(ok_results) == 3
        assert patched["view"]["outputs"]["parameters"]["subnets"] == new_subnets
        assert patched["view"]["outputs"]["parameters"]["vnetAddressPrefix"] == ["10.2.5.64/26"]

    def test_patch_adds_new_output_param(self, sample_ui_definition: dict) -> None:
        """Test that a new parameter is added if it doesn't exist."""
        output_patches = [
            {"parameter_name": "newCustomParam", "value": "customValue"},
        ]
        patched, results = _apply_output_patches(sample_ui_definition, output_patches)

        assert "OK_ADDED: outputs.parameters.newCustomParam" in results
        assert patched["view"]["outputs"]["parameters"]["newCustomParam"] == "customValue"

    def test_patch_missing_parameter_name_skipped(self, sample_ui_definition: dict) -> None:
        """Test that patches without parameter_name are skipped."""
        output_patches = [
            {"value": "test"},
        ]
        _, results = _apply_output_patches(sample_ui_definition, output_patches)

        assert any("SKIP" in r for r in results)

    def test_patch_no_outputs_section(self) -> None:
        """Test handling when the outputs section doesn't exist."""
        ui_def = {"view": {"properties": {"steps": []}}}
        output_patches = [
            {"parameter_name": "subnets", "value": []},
        ]
        _, results = _apply_output_patches(ui_def, output_patches)

        assert any("NOT_FOUND" in r for r in results)


class TestIntegration:
    """Integration tests that write actual files."""

    def test_full_patch_workflow(self, sample_ui_definition: dict) -> None:
        """Test a full patch workflow including file I/O."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write source file
            source_path = Path(tmpdir) / "source.json"
            source_path.write_text(json.dumps(sample_ui_definition, indent=2))

            # Apply patches
            patches = [
                {"step_name": "basics", "element_path": "agency", "value": "MIN69"},
                {"step_name": "basics", "element_path": "project", "value": "RG169"},
            ]

            # Load, patch, and write
            ui_def = json.loads(source_path.read_text())
            patched, results = _apply_patches(ui_def, patches)

            output_path = Path(tmpdir) / "output.json"
            output_path.write_text(json.dumps(patched, indent=2))

            # Verify output
            assert output_path.exists()
            result_def = json.loads(output_path.read_text())

            agency = _find_element_in_steps(result_def, "basics", "agency")
            assert agency["defaultValue"] == "MIN69"

            project = _find_element_in_steps(result_def, "basics", "project")
            assert project["defaultValue"] == "RG169"
