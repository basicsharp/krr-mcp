"""Tests for documentation generator."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.documentation.tool_doc_generator import ToolDocumentationGenerator
from src.server import KrrMCPServer, ServerConfig


class TestToolDocumentationGenerator:
    """Test ToolDocumentationGenerator class."""
    
    @pytest.fixture
    def mock_server(self):
        """Create a mock server instance."""
        config = ServerConfig(
            development_mode=True,
            mock_krr_responses=True,
            mock_kubectl_commands=True,
        )
        return MagicMock(spec=KrrMCPServer)
    
    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary output directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def doc_generator(self, mock_server, temp_output_dir):
        """Create a documentation generator instance."""
        return ToolDocumentationGenerator(mock_server, temp_output_dir)
    
    def test_generator_initialization(self, doc_generator, mock_server, temp_output_dir):
        """Test documentation generator initialization."""
        assert doc_generator.server == mock_server
        assert doc_generator.output_dir == temp_output_dir
        assert temp_output_dir.exists()
    
    def test_extract_tools_info(self, doc_generator):
        """Test extracting tools information."""
        tools_info = doc_generator._extract_tools_info()
        
        # Verify all expected tools are present
        expected_tools = {
            "scan_recommendations",
            "preview_changes", 
            "request_confirmation",
            "apply_recommendations",
            "rollback_changes",
            "get_safety_report",
            "get_execution_history",
        }
        
        assert set(tools_info.keys()) == expected_tools
        
        # Verify tool structure
        for tool_name, tool_info in tools_info.items():
            assert "description" in tool_info
            assert "parameters" in tool_info
            assert "returns" in tool_info
            assert "safety_level" in tool_info
            
            # Verify safety-critical tools have proper notices
            if tool_name in ["apply_recommendations", "rollback_changes"]:
                assert "critical_notice" in tool_info
                assert "SAFETY CRITICAL" in tool_info["critical_notice"]
    
    def test_generate_safety_documentation(self, doc_generator):
        """Test safety documentation generation."""
        safety_docs = doc_generator._generate_safety_documentation()
        
        assert "overview" in safety_docs
        assert "safety_levels" in safety_docs
        assert "safety_guarantees" in safety_docs
        assert "confirmation_workflow" in safety_docs
        
        # Verify safety levels
        expected_levels = ["read_only", "analysis_only", "confirmation_required", "cluster_modification"]
        assert set(safety_docs["safety_levels"].keys()) == set(expected_levels)
        
        # Verify safety guarantees
        guarantees = safety_docs["safety_guarantees"]
        assert len(guarantees) >= 8
        assert any("No recommendations applied without explicit user confirmation" in g for g in guarantees)
        assert any("Complete audit trail" in g for g in guarantees)
    
    def test_generate_usage_examples(self, doc_generator):
        """Test usage examples generation."""
        examples = doc_generator._generate_usage_examples()
        
        assert "basic_workflow" in examples
        assert "safety_scenarios" in examples
        
        # Verify basic workflow
        workflow = examples["basic_workflow"]
        assert "steps" in workflow
        assert len(workflow["steps"]) >= 4
        
        # Verify step structure
        for step in workflow["steps"]:
            assert "step" in step
            assert "action" in step
            assert "tool" in step
            assert "example" in step
    
    def test_generate_error_codes_documentation(self, doc_generator):
        """Test error codes documentation generation."""
        error_docs = doc_generator._generate_error_codes_documentation()
        
        assert "overview" in error_docs
        assert "error_codes" in error_docs
        assert "error_handling_best_practices" in error_docs
        
        # Verify common error codes
        error_codes = error_docs["error_codes"]
        expected_codes = [
            "COMPONENT_NOT_READY",
            "INVALID_STRATEGY", 
            "INVALID_TOKEN",
            "EXECUTION_FAILED",
        ]
        
        for code in expected_codes:
            assert code in error_codes
            assert "description" in error_codes[code]
            assert "resolution" in error_codes[code]
    
    def test_generate_full_documentation(self, doc_generator):
        """Test full documentation generation."""
        documentation = doc_generator.generate_full_documentation()
        
        # Verify top-level structure
        assert "metadata" in documentation
        assert "tools" in documentation
        assert "safety_features" in documentation
        assert "examples" in documentation
        assert "error_codes" in documentation
        
        # Verify metadata
        metadata = documentation["metadata"]
        assert "server_name" in metadata
        assert "version" in metadata
        assert "generated_at" in metadata
        assert "safety_notice" in metadata
        
        # Verify tools count
        assert len(documentation["tools"]) >= 7
    
    def test_write_markdown_documentation(self, doc_generator):
        """Test Markdown documentation writing."""
        documentation = doc_generator.generate_full_documentation()
        
        # Check that files were created
        expected_files = [
            "api-reference.md",
            "safety-guide.md",
            "usage-examples.md",
        ]
        
        for filename in expected_files:
            file_path = doc_generator.output_dir / filename
            assert file_path.exists()
            
            # Verify file has content
            content = file_path.read_text()
            assert len(content) > 100  # Should have substantial content
            assert "# " in content  # Should have markdown headers
    
    def test_write_json_documentation(self, doc_generator):
        """Test JSON documentation writing."""
        doc_generator.generate_full_documentation()
        
        json_file = doc_generator.output_dir / "api-documentation.json"
        assert json_file.exists()
        
        # Verify JSON is valid and has expected structure
        with open(json_file) as f:
            json_data = json.load(f)
        
        assert "metadata" in json_data
        assert "tools" in json_data
        assert len(json_data["tools"]) >= 7
    
    def test_write_openapi_specification(self, doc_generator):
        """Test OpenAPI specification writing."""
        doc_generator.generate_full_documentation()
        
        openapi_file = doc_generator.output_dir / "openapi.json"
        assert openapi_file.exists()
        
        # Verify OpenAPI spec is valid
        with open(openapi_file) as f:
            openapi_spec = json.load(f)
        
        assert openapi_spec["openapi"] == "3.0.0"
        assert "info" in openapi_spec
        assert "paths" in openapi_spec
        assert "components" in openapi_spec
        
        # Verify tool paths
        paths = openapi_spec["paths"]
        assert len(paths) >= 7
        
        for path in paths.keys():
            assert path.startswith("/tools/")
    
    def test_generate_markdown_content(self, doc_generator):
        """Test Markdown content generation."""
        documentation = doc_generator.generate_full_documentation()
        content = doc_generator._generate_markdown_content(documentation)
        
        # Verify content structure
        assert "# krr MCP Server API Reference" in content
        assert "## ⚠️ SAFETY NOTICE" in content
        assert "## Available Tools" in content
        
        # Verify tool sections
        for tool_name in documentation["tools"].keys():
            assert f"### {tool_name}" in content
        
        # Verify safety critical notices
        assert "SAFETY CRITICAL" in content
    
    def test_convert_parameters_to_openapi(self, doc_generator):
        """Test parameter conversion to OpenAPI format."""
        parameters = {
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace",
                "required": False,
            },
            "strategy": {
                "type": "string",
                "description": "krr strategy",
                "required": True, 
                "enum": ["simple", "medium", "aggressive"],
                "default": "simple",
            },
        }
        
        openapi_params = doc_generator._convert_parameters_to_openapi(parameters)
        
        assert len(openapi_params) == 2
        
        # Verify namespace parameter
        namespace_param = next(p for p in openapi_params if p["name"] == "namespace")
        assert namespace_param["required"] is False
        assert namespace_param["schema"]["type"] == "string"
        
        # Verify strategy parameter
        strategy_param = next(p for p in openapi_params if p["name"] == "strategy")
        assert strategy_param["required"] is True
        assert "enum" in strategy_param["schema"]
        assert "default" in strategy_param["schema"]