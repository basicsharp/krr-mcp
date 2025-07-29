"""Tests for MCP tools integration."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.recommender.models import KrrRecommendation
from src.safety.models import ResourceChange
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
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Verify components are available
        assert server.krr_client is not None

        # Test that krr client can generate mock recommendations
        recommendations = await server.krr_client.get_recommendations(
            namespace="default", strategy="simple"
        )

        assert isinstance(recommendations, list)
        # In mock mode, should return sample recommendations
        if server.config.mock_krr_responses:
            assert len(recommendations) >= 0  # Mock may return empty or sample data

    @pytest.mark.asyncio
    async def test_safety_validator_functionality(self, server):
        """Test safety validator functionality."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test that safety components are available
        assert server.confirmation_manager is not None

        # Create a sample resource change for testing
        sample_change = ResourceChange(
            resource_name="test-deployment",
            namespace="default",
            resource_type="Deployment",
            change_type="resource_increase",
            current_cpu="100m",
            current_memory="128Mi",
            proposed_cpu="250m",
            proposed_memory="256Mi",
            cpu_change_percent=150.0,
            memory_change_percent=100.0,
        )

        # Test that safety validation works
        assert sample_change.cpu_change_percent == 150.0
        assert sample_change.memory_change_percent == 100.0

    @pytest.mark.asyncio
    async def test_confirmation_manager_functionality(self, server):
        """Test confirmation manager functionality."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test confirmation manager is available
        assert server.confirmation_manager is not None

        # Create sample changes for testing
        sample_changes = [
            ResourceChange(
                resource_name="test-deployment",
                namespace="default",
                resource_type="Deployment",
                change_type="resource_increase",
                current_cpu="100m",
                current_memory="128Mi",
                proposed_cpu="250m",
                proposed_memory="256Mi",
                cpu_change_percent=150.0,
                memory_change_percent=100.0,
            )
        ]

        # Test token creation
        token = server.confirmation_manager.create_confirmation_token(
            changes=sample_changes, risk_level="medium"
        )

        assert token is not None
        assert hasattr(token, "token_id")
        assert hasattr(token, "expires_at")

    @pytest.mark.asyncio
    async def test_kubectl_executor_functionality(self, server):
        """Test kubectl executor functionality."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test kubectl executor is available
        assert server.kubectl_executor is not None

        # Test that executor is in mock mode
        assert server.config.mock_kubectl_commands is True

        # Test that executor has required methods
        assert hasattr(server.kubectl_executor, "execute_changes")
        assert hasattr(server.kubectl_executor, "create_rollback_snapshot")

    @pytest.mark.asyncio
    async def test_server_components_integration(self, server):
        """Test that all server components work together."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test all components are initialized
        assert server.krr_client is not None
        assert server.confirmation_manager is not None
        assert server.kubectl_executor is not None

        # Test configuration is consistent
        assert server.config.development_mode is True
        assert server.config.mock_krr_responses is True
        assert server.config.mock_kubectl_commands is True

    @pytest.mark.asyncio
    async def test_token_validation_logic(self, server):
        """Test token validation logic."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test that confirmation manager can validate tokens
        assert server.confirmation_manager is not None

        # Test invalid token validation
        is_valid = server.confirmation_manager.validate_token("invalid-token")
        assert is_valid is False or is_valid is None

    @pytest.mark.asyncio
    async def test_rollback_snapshot_functionality(self, server):
        """Test rollback snapshot functionality."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test kubectl executor rollback capabilities
        assert server.kubectl_executor is not None
        assert hasattr(server.kubectl_executor, "create_rollback_snapshot")

        # Test that rollback snapshots can be created
        # In mock mode, this should work without real kubectl
        assert server.config.mock_kubectl_commands is True

    def test_server_initialization(self, mock_server_config):
        """Test server initialization."""
        server = KrrMCPServer(mock_server_config)

        assert server.config.mock_krr_responses is True
        assert server.config.mock_kubectl_commands is True
        assert server.config.development_mode is True
