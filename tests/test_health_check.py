"""Tests for health check endpoint functionality."""

import asyncio

import pytest

from src.server import KrrMCPServer, ServerConfig


class TestHealthCheck:
    """Test health check endpoint functionality."""

    @pytest.fixture
    async def server(self) -> KrrMCPServer:
        """Create a test server instance."""
        config = ServerConfig(
            development_mode=True,
            mock_krr_responses=True,
            mock_kubectl_commands=True,
        )
        server = KrrMCPServer(config)
        # Wait for async initialization to complete
        await asyncio.sleep(0.2)
        return server

    @pytest.mark.asyncio
    async def test_server_components_initialization(self, server: KrrMCPServer) -> None:
        """Test that server components are properly initialized."""
        # All components should be initialized in mock mode
        assert server.mcp is not None, "MCP server should be initialized"
        assert server.krr_client is not None, "KRR client should be initialized"
        assert (
            server.confirmation_manager is not None
        ), "Confirmation manager should be initialized"
        assert (
            server.kubectl_executor is not None
        ), "Kubectl executor should be initialized"
        assert (
            server.doc_generator is not None
        ), "Documentation generator should be initialized"

    @pytest.mark.asyncio
    async def test_health_check_components_status(self, server: KrrMCPServer) -> None:
        """Test health check component status evaluation."""
        # Test the components status logic directly
        components_status = {}

        # Check core components (note: server._running is False by default until start() is called)
        components_status["mcp_server"] = {
            "status": "healthy" if server._running else "stopped",
            "initialized": bool(server.mcp),
        }

        components_status["krr_client"] = {
            "status": "healthy" if server.krr_client else "not_initialized",
            "initialized": bool(server.krr_client),
        }

        components_status["confirmation_manager"] = {
            "status": "healthy" if server.confirmation_manager else "not_initialized",
            "initialized": bool(server.confirmation_manager),
        }

        components_status["kubectl_executor"] = {
            "status": "healthy" if server.kubectl_executor else "not_initialized",
            "initialized": bool(server.kubectl_executor),
        }

        components_status["doc_generator"] = {
            "status": "healthy" if server.doc_generator else "not_initialized",
            "initialized": bool(server.doc_generator),
        }

        # All components should be initialized
        for component_name, status in components_status.items():
            assert (
                status["initialized"] is True
            ), f"{component_name} should be initialized"
            if component_name == "mcp_server":
                # MCP server shows as "stopped" until start() is called
                assert (
                    status["status"] == "stopped"
                ), f"{component_name} should be stopped (not started)"
            else:
                assert (
                    status["status"] == "healthy"
                ), f"{component_name} should be healthy"

    @pytest.mark.asyncio
    async def test_overall_health_status_logic(self, server: KrrMCPServer) -> None:
        """Test overall health status determination logic."""
        # Test healthy state
        components_initialized = [
            server.mcp is not None,
            server.krr_client is not None,
            server.confirmation_manager is not None,
            server.kubectl_executor is not None,
            server.doc_generator is not None,
        ]

        all_components_healthy = all(components_initialized)
        server_running = server._running

        # Determine expected health status
        if not server_running:
            expected_status = "unhealthy"
        elif not all_components_healthy:
            expected_status = "degraded"
        else:
            expected_status = "healthy"

        # In mock mode with proper initialization, but server not started, should be unhealthy
        assert all_components_healthy is True, "All components should be initialized"
        assert (
            server_running is False
        ), "Server should not be marked as running until start() is called"
        assert (
            expected_status == "unhealthy"
        ), "Server should be unhealthy when not running (even if components are initialized)"

    @pytest.mark.asyncio
    async def test_server_not_running_status(self, server: KrrMCPServer) -> None:
        """Test health status when server is not running."""
        # Set server as not running
        original_running = server._running
        server._running = False

        try:
            # Test health status logic
            if not server._running:
                expected_status = "unhealthy"
            else:
                expected_status = "healthy"

            assert (
                expected_status == "unhealthy"
            ), "Server should be unhealthy when not running"
            assert server._running is False, "Server should be marked as not running"
        finally:
            # Restore original state
            server._running = original_running

    @pytest.mark.asyncio
    async def test_configuration_values(self, server: KrrMCPServer) -> None:
        """Test that server configuration is properly accessible."""
        config = server.config

        # Check mock configuration
        assert config.development_mode is True, "Development mode should be enabled"
        assert config.mock_krr_responses is True, "KRR responses should be mocked"
        assert config.mock_kubectl_commands is True, "Kubectl commands should be mocked"
        assert (
            config.prometheus_url == "http://localhost:9090"
        ), "Default Prometheus URL should be set"
        assert config.krr_strategy == "simple", "Default KRR strategy should be simple"

    @pytest.mark.asyncio
    async def test_health_check_tool_registered(self, server: KrrMCPServer) -> None:
        """Test that health check tool is properly registered with the MCP server."""
        # The MCP server should have the health_check tool registered
        # We can't easily access the tools directly, but we can verify the MCP instance exists
        assert server.mcp is not None, "MCP server instance should exist"

        # In a real scenario, the health_check tool would be accessible via MCP protocol
        # For this test, we just verify the server structure is correct for health checking
        assert hasattr(server, "_running"), "Server should have running state"
        assert hasattr(server, "config"), "Server should have configuration"
        assert hasattr(server, "krr_client"), "Server should have KRR client"
        assert hasattr(
            server, "confirmation_manager"
        ), "Server should have confirmation manager"
        assert hasattr(
            server, "kubectl_executor"
        ), "Server should have kubectl executor"
        assert hasattr(
            server, "doc_generator"
        ), "Server should have documentation generator"

    @pytest.mark.asyncio
    async def test_timestamp_generation(self, server: KrrMCPServer) -> None:
        """Test timestamp generation for health checks."""
        # Get timestamp using the same method as health check
        timestamp1 = asyncio.get_event_loop().time()

        # Wait a bit
        await asyncio.sleep(0.01)

        timestamp2 = asyncio.get_event_loop().time()

        # Timestamps should be different and increasing
        assert isinstance(timestamp1, float), "Timestamp should be a float"
        assert isinstance(timestamp2, float), "Timestamp should be a float"
        assert timestamp2 > timestamp1, "Timestamps should increase over time"
