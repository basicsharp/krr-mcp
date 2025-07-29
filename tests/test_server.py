"""Tests for the main server implementation."""

import pytest
from unittest.mock import AsyncMock, patch

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
        with patch.dict('os.environ', {
            'PROMETHEUS_URL': 'http://custom:9090',
            'KRR_STRATEGY': 'aggressive',
            'CONFIRMATION_TIMEOUT_SECONDS': '600',
            'DEVELOPMENT_MODE': 'true',
        }):
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
        with patch.object(test_server.mcp, 'run', new_callable=AsyncMock) as mock_run:
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
        
        with patch.object(test_server.logger, 'warning') as mock_warning:
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
    async def test_scan_recommendations_tool(self, test_server):
        """Test the scan_recommendations tool."""
        # Access the tool through the server's MCP instance
        # Note: This is a basic test - the actual implementation will be added later
        
        # For now, we're testing that the tool is registered and has basic structure
        assert hasattr(test_server, 'mcp')
        assert test_server.mcp is not None
    
    @pytest.mark.asyncio
    async def test_preview_changes_tool(self, test_server):
        """Test the preview_changes tool."""
        # Placeholder test for the preview tool
        # Will be expanded when the actual implementation is added
        pass
    
    @pytest.mark.asyncio
    async def test_request_confirmation_tool(self, test_server):
        """Test the request_confirmation tool."""
        # Placeholder test for the confirmation tool
        # This is safety-critical and will need comprehensive testing
        pass
    
    @pytest.mark.asyncio
    async def test_apply_recommendations_tool(self, test_server):
        """Test the apply_recommendations tool."""
        # Placeholder test for the apply tool
        # This is the most safety-critical tool and needs extensive testing
        pass


class TestSafetyIntegration:
    """Test safety-related functionality."""
    
    @pytest.mark.asyncio
    async def test_no_direct_execution_path(self, test_server):
        """Test that there's no direct path from recommendation to execution."""
        # This test will verify that the apply_recommendations tool
        # always requires a valid confirmation token
        # Implementation pending safety module
        pass
    
    @pytest.mark.asyncio
    async def test_confirmation_token_validation(self, test_server):
        """Test confirmation token validation."""
        # Test that invalid tokens are rejected
        # Test that expired tokens are rejected
        # Test that tokens can only be used once
        # Implementation pending safety module
        pass
    
    @pytest.mark.asyncio
    async def test_rollback_capability(self, test_server):
        """Test rollback functionality."""
        # Test that rollback information is captured
        # Test that rollback can be executed
        # Test that rollback requires confirmation
        # Implementation pending safety module
        pass


class TestErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_krr_not_found_error(self, test_server):
        """Test handling when krr CLI is not available."""
        # Implementation pending krr integration
        pass
    
    @pytest.mark.asyncio 
    async def test_kubernetes_connection_error(self, test_server):
        """Test handling of Kubernetes connection failures."""
        # Implementation pending Kubernetes integration
        pass
    
    @pytest.mark.asyncio
    async def test_prometheus_connection_error(self, test_server):
        """Test handling of Prometheus connection failures."""
        # Implementation pending Prometheus integration
        pass
    
    @pytest.mark.asyncio
    async def test_partial_execution_failure(self, test_server):
        """Test handling of partial execution failures."""
        # Test scenario where some resources update successfully but others fail
        # Implementation pending executor module
        pass


class TestAuditTrail:
    """Test audit trail functionality."""
    
    @pytest.mark.asyncio
    async def test_operation_logging(self, test_server, caplog_structured):
        """Test that all operations are properly logged."""
        # Test that confirmation requests are logged
        # Test that execution attempts are logged
        # Test that results are logged
        # Implementation pending full tool implementation
        pass
    
    @pytest.mark.asyncio
    async def test_structured_logging_format(self, test_server, caplog_structured):
        """Test that logs are in proper structured format."""
        # Verify logs contain required fields for audit
        # Implementation pending full tool implementation
        pass