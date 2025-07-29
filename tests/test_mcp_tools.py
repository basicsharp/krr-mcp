"""Tests for MCP tools integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.server import KrrMCPServer, ServerConfig


class TestMCPTools:
    """Test MCP tools implementation."""
    
    @pytest.fixture
    def mock_server_config(self):
        """Create a test server configuration."""
        return ServerConfig(
            kubeconfig="/tmp/test-kubeconfig",
            kubernetes_context="test-context",
            prometheus_url="http://localhost:9090",
            mock_krr_responses=True,
            mock_kubectl_commands=True,
            development_mode=True,
        )
    
    @pytest.fixture
    async def server(self, mock_server_config):
        """Create a test server instance."""
        server = KrrMCPServer(mock_server_config)
        
        # Wait for async initialization
        import asyncio
        await asyncio.sleep(0.1)  # Allow initialization to complete
        
        return server
    
    @pytest.mark.asyncio
    async def test_scan_recommendations_tool(self, server):
        """Test scan_recommendations MCP tool."""
        # Access the tool function directly
        tools = {}
        
        # Mock the tool registration to capture the functions
        original_tool = server.mcp.tool
        def mock_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator
        
        server.mcp.tool = mock_tool
        server._register_tools()
        
        # Test the scan_recommendations function
        scan_func = tools.get('scan_recommendations')
        assert scan_func is not None
        
        result = await scan_func(namespace="default", strategy="simple")
        
        assert result["status"] == "success"
        assert "recommendations" in result
        assert "metadata" in result
        assert result["metadata"]["namespace"] == "default"
        assert result["metadata"]["strategy"] == "simple"
    
    @pytest.mark.asyncio
    async def test_preview_changes_tool(self, server):
        """Test preview_changes MCP tool."""
        tools = {}
        
        # Mock the tool registration
        original_tool = server.mcp.tool
        def mock_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator
        
        server.mcp.tool = mock_tool
        server._register_tools()
        
        # Test with sample recommendations
        sample_recommendations = [
            {
                "object": {
                    "kind": "Deployment",
                    "name": "test-app",
                    "namespace": "default"
                },
                "current": {
                    "requests": {
                        "cpu": "100m",
                        "memory": "128Mi"
                    }
                },
                "recommended": {
                    "requests": {
                        "cpu": "250m",
                        "memory": "256Mi"
                    }
                }
            }
        ]
        
        preview_func = tools.get('preview_changes')
        assert preview_func is not None
        
        result = await preview_func(sample_recommendations)
        
        assert result["status"] == "success"
        assert "preview" in result
        assert result["preview"]["total_resources_affected"] == 1
        assert len(result["preview"]["changes"]) == 1
        
        change = result["preview"]["changes"][0]
        assert change["resource"] == "Deployment/test-app"
        assert change["namespace"] == "default"
        assert change["current_cpu"] == "100m"
        assert change["proposed_cpu"] == "250m"
    
    @pytest.mark.asyncio
    async def test_request_confirmation_tool(self, server):
        """Test request_confirmation MCP tool."""
        tools = {}
        
        # Mock the tool registration
        original_tool = server.mcp.tool
        def mock_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator
        
        server.mcp.tool = mock_tool
        server._register_tools()
        
        # Test with sample changes
        sample_changes = {
            "changes": [
                {
                    "resource": "Deployment/test-app",
                    "namespace": "default",
                    "change_type": "resource_increase",
                    "current_cpu": "100m",
                    "current_memory": "128Mi",
                    "proposed_cpu": "250m",
                    "proposed_memory": "256Mi",
                    "cpu_change_percent": 150.0,
                    "memory_change_percent": 100.0,
                }
            ]
        }
        
        confirmation_func = tools.get('request_confirmation')
        assert confirmation_func is not None
        
        result = await confirmation_func(sample_changes)
        
        assert result["status"] == "success"
        assert result["confirmation_required"] is True
        assert "confirmation_token" in result
        assert "confirmation_prompt" in result
        assert "safety_assessment" in result
    
    @pytest.mark.asyncio
    async def test_get_safety_report_tool(self, server):
        """Test get_safety_report MCP tool."""
        tools = {}
        
        # Mock the tool registration
        original_tool = server.mcp.tool
        def mock_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator
        
        server.mcp.tool = mock_tool
        server._register_tools()
        
        # Test with sample changes
        sample_changes = {
            "changes": [
                {
                    "resource": "Deployment/test-app",
                    "namespace": "default",
                    "change_type": "resource_increase",
                    "current_cpu": "100m",
                    "current_memory": "128Mi",
                    "proposed_cpu": "250m",
                    "proposed_memory": "256Mi",
                }
            ]
        }
        
        safety_func = tools.get('get_safety_report')
        assert safety_func is not None
        
        result = await safety_func(sample_changes)
        
        assert result["status"] == "success"
        assert "safety_report" in result
        
        report = result["safety_report"]
        assert "overall_risk_level" in report
        assert "total_resources_affected" in report
        assert "warnings" in report
    
    @pytest.mark.asyncio
    async def test_get_execution_history_tool(self, server):
        """Test get_execution_history MCP tool."""
        tools = {}
        
        # Mock the tool registration
        original_tool = server.mcp.tool
        def mock_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator
        
        server.mcp.tool = mock_tool
        server._register_tools()
        
        history_func = tools.get('get_execution_history')
        assert history_func is not None
        
        result = await history_func(limit=5)
        
        assert result["status"] == "success"
        assert "history" in result
        assert "total_count" in result
        assert result["filters_applied"]["limit"] == 5
    
    @pytest.mark.asyncio 
    async def test_apply_recommendations_invalid_token(self, server):
        """Test apply_recommendations with invalid token."""
        tools = {}
        
        # Mock the tool registration
        original_tool = server.mcp.tool
        def mock_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator
        
        server.mcp.tool = mock_tool
        server._register_tools()
        
        apply_func = tools.get('apply_recommendations')
        assert apply_func is not None
        
        result = await apply_func("invalid-token", dry_run=True)
        
        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_TOKEN"
    
    @pytest.mark.asyncio
    async def test_rollback_changes_invalid_id(self, server):
        """Test rollback_changes with invalid rollback ID."""
        tools = {}
        
        # Mock the tool registration
        original_tool = server.mcp.tool
        def mock_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator
        
        server.mcp.tool = mock_tool
        server._register_tools()
        
        rollback_func = tools.get('rollback_changes')
        assert rollback_func is not None
        
        result = await rollback_func("invalid-rollback-id", "invalid-token")
        
        assert result["status"] == "error"
        # Should fail on token validation first
        assert result["error_code"] in ["INVALID_TOKEN", "TOKEN_NOT_FOUND"]
    
    def test_server_initialization(self, mock_server_config):
        """Test server initialization."""
        server = KrrMCPServer(mock_server_config)
        
        assert server.config.mock_krr_responses is True
        assert server.config.mock_kubectl_commands is True
        assert server.config.development_mode is True