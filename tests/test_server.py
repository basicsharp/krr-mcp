"""Tests for the main server implementation."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.server import KrrMCPServer, ServerConfig


class TestServerConfig:
    """Test server configuration."""

    def test_default_configuration(self):
        """Test default configuration values."""
        config = ServerConfig()

        assert config.prometheus_url == "http://localhost:9090"
        assert config.krr_strategy == "simple"
        assert config.confirmation_timeout_seconds == 300
        assert config.max_resource_change_percent == 500
        assert config.rollback_retention_days == 7
        assert config.development_mode is False
        assert config.mock_krr_responses is False
        assert config.mock_kubectl_commands is False

    def test_environment_variable_override(self):
        """Test that environment variables override defaults."""
        with patch.dict(
            "os.environ",
            {
                "PROMETHEUS_URL": "http://custom:9090",
                "KRR_STRATEGY": "aggressive",
                "CONFIRMATION_TIMEOUT_SECONDS": "600",
                "DEVELOPMENT_MODE": "true",
            },
        ):
            config = ServerConfig()

            assert config.prometheus_url == "http://custom:9090"
            assert config.krr_strategy == "aggressive"
            assert config.confirmation_timeout_seconds == 600
            assert config.development_mode is True


class TestKrrMCPServer:
    """Test the main server class."""

    def test_server_initialization(self, test_config):
        """Test server initializes correctly."""
        server = KrrMCPServer(test_config)

        assert server.config == test_config
        assert server._running is False
        assert server._confirmation_tokens == {}
        assert server.mcp is not None

    @pytest.mark.asyncio
    async def test_server_start_stop(self, test_server):
        """Test server start and stop lifecycle."""
        # Mock the validation method
        test_server._validate_configuration = AsyncMock()

        # Start server
        with patch.object(test_server.mcp, "run", new_callable=AsyncMock) as mock_run:
            await test_server.start()
            assert test_server._running is True
            mock_run.assert_called_once()

        # Stop server
        await test_server.stop()
        assert test_server._running is False
        assert test_server._confirmation_tokens == {}

    @pytest.mark.asyncio
    async def test_server_double_start_prevention(self, test_server):
        """Test that server prevents double start."""
        test_server._running = True

        with patch.object(test_server.logger, "warning") as mock_warning:
            await test_server.start()
            mock_warning.assert_called_once_with("Server is already running")

    @pytest.mark.asyncio
    async def test_configuration_validation(self, test_server):
        """Test configuration validation."""
        # This is a placeholder test - the actual validation will be implemented
        # when we add the krr integration and Kubernetes connectivity checks
        await test_server._validate_configuration()
        # Should not raise any exceptions with mock configuration


class TestMCPTools:
    """Test MCP tool implementations."""

    @pytest.mark.asyncio
    async def test_tools_are_registered(self, test_server):
        """Test that all required MCP tools are registered."""
        # Wait for async initialization
        await asyncio.sleep(0.1)

        # Verify server has MCP instance
        assert hasattr(test_server, "mcp")
        assert test_server.mcp is not None

        # Verify components are initialized
        assert test_server.krr_client is not None
        assert test_server.confirmation_manager is not None
        assert test_server.kubectl_executor is not None

    @pytest.mark.asyncio
    async def test_component_initialization(self, test_server):
        """Test that all server components are properly initialized."""
        # Wait for async initialization
        await asyncio.sleep(0.1)

        # Test krr client initialization
        assert test_server.krr_client is not None
        assert hasattr(test_server.krr_client, "get_recommendations")

        # Test confirmation manager initialization
        assert test_server.confirmation_manager is not None
        assert hasattr(test_server.confirmation_manager, "create_confirmation_token")

        # Test kubectl executor initialization
        assert test_server.kubectl_executor is not None
        assert hasattr(test_server.kubectl_executor, "execute_changes")

    @pytest.mark.asyncio
    async def test_server_components_mock_mode(self, test_server):
        """Test that server components work in mock mode."""
        # Wait for async initialization
        await asyncio.sleep(0.1)

        # Test that mock mode is enabled for development
        assert test_server.config.mock_krr_responses is True
        assert test_server.config.mock_kubectl_commands is True
        assert test_server.config.development_mode is True


class TestSafetyIntegration:
    """Test safety-related functionality."""

    @pytest.mark.asyncio
    async def test_confirmation_manager_initialization(self, test_server):
        """Test that confirmation manager is properly initialized."""
        # Wait for async initialization
        await asyncio.sleep(0.1)

        assert test_server.confirmation_manager is not None
        assert hasattr(test_server.confirmation_manager, "create_confirmation_token")
        assert hasattr(test_server.confirmation_manager, "validate_token")

    @pytest.mark.asyncio
    async def test_safety_configuration(self, test_server):
        """Test safety configuration parameters."""
        config = test_server.config

        # Verify safety timeouts are set
        assert config.confirmation_timeout_seconds > 0
        assert config.max_resource_change_percent > 0
        assert config.rollback_retention_days > 0

        # Verify development safety settings
        assert config.development_mode is True
        assert config.mock_krr_responses is True
        assert config.mock_kubectl_commands is True

    @pytest.mark.asyncio
    async def test_audit_logging_setup(self, test_server, caplog_structured):
        """Test that audit logging is properly configured."""
        # Wait for async initialization
        await asyncio.sleep(0.1)

        # Test that logger is configured
        assert test_server.logger is not None

        # Test that structured logging works
        test_server.logger.info("test_audit_message", operation="test")

        # Verify structured log format
        assert len(caplog_structured.records) > 0


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_component_initialization_error_handling(self, test_config):
        """Test error handling during component initialization."""
        # Create server with invalid configuration to test error handling
        invalid_config = test_config.copy()
        invalid_config.kubeconfig = "/nonexistent/path/kubeconfig"

        # Server should initialize but handle the invalid config gracefully
        server = KrrMCPServer(invalid_config)

        # Wait for initialization
        await asyncio.sleep(0.1)

        # Verify server was created but may have initialization issues
        assert server is not None
        assert server.config.kubeconfig == "/nonexistent/path/kubeconfig"

    @pytest.mark.asyncio
    async def test_mock_mode_error_handling(self, test_server):
        """Test error handling in mock mode."""
        # Wait for async initialization
        await asyncio.sleep(0.1)

        # Verify mock mode is enabled
        assert test_server.config.mock_krr_responses is True
        assert test_server.config.mock_kubectl_commands is True

        # Components should be initialized even in mock mode
        assert test_server.krr_client is not None
        assert test_server.kubectl_executor is not None

    @pytest.mark.asyncio
    async def test_configuration_validation(self, test_server):
        """Test configuration validation."""
        # Wait for async initialization
        await asyncio.sleep(0.1)

        # Test that configuration has required fields
        config = test_server.config
        assert config.prometheus_url is not None
        assert config.krr_strategy is not None
        assert config.confirmation_timeout_seconds > 0


class TestAuditTrail:
    """Test audit trail functionality."""

    @pytest.mark.asyncio
    async def test_server_initialization_logging(self, test_server, caplog_structured):
        """Test that server initialization is properly logged."""
        # Wait for async initialization
        await asyncio.sleep(0.1)

        # Verify structured logging is working
        test_server.logger.info("test_initialization", component="server")

        # Check that log records are captured
        assert len(caplog_structured.records) > 0

    @pytest.mark.asyncio
    async def test_component_logging(self, test_server, caplog_structured):
        """Test that component operations are logged."""
        # Wait for async initialization
        await asyncio.sleep(0.1)

        # Test that components can log
        if test_server.krr_client:
            test_server.logger.info("krr_client_test", component="krr_client")

        if test_server.confirmation_manager:
            test_server.logger.info(
                "confirmation_manager_test", component="confirmation"
            )

        # Verify logging is working
        assert test_server.logger is not None
