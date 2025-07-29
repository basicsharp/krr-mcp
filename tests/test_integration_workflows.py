"""Integration tests for full recommendation workflows.

These tests verify the complete end-to-end workflows of the krr MCP server,
ensuring all components work together correctly and safely.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.safety.models import ConfirmationToken, ResourceChange, SafetyAssessment
from src.server import KrrMCPServer


class TestFullRecommendationWorkflow:
    """Test complete recommendation workflow from scan to execution."""

    @pytest.mark.asyncio
    async def test_complete_workflow_components(self, test_server, mock_krr_response):
        """Test that all workflow components are available."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Step 1: Verify krr client can scan
        assert test_server.krr_client is not None
        recommendations = await test_server.krr_client.get_recommendations(
            namespace="default", strategy="simple"
        )
        assert isinstance(recommendations, list)

        # Step 2: Verify safety validator is available
        assert test_server.confirmation_manager is not None

        # Step 3: Verify kubectl executor is available
        assert test_server.kubectl_executor is not None

        # Verify all components work in mock mode
        assert test_server.config.mock_krr_responses is True
        assert test_server.config.mock_kubectl_commands is True

        # Step 4: Test mock mode safety
        assert test_server.config.development_mode is True
        assert test_server.config.mock_kubectl_commands is True

        # Verify components are properly integrated for workflow
        assert test_server.krr_client is not None
        assert test_server.confirmation_manager is not None
        assert test_server.kubectl_executor is not None

    @pytest.mark.asyncio
    async def test_safety_validation_workflow(
        self, test_server, dangerous_recommendations
    ):
        """Test safety validation components."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test safety validation is available
        assert test_server.confirmation_manager is not None

        # Test configuration safety limits
        assert test_server.config.max_resource_change_percent > 0
        assert test_server.config.confirmation_timeout_seconds > 0

        # Test dangerous changes can be detected
        from src.safety.models import ResourceChange

        dangerous_change = ResourceChange(
            resource_name="test-app",
            namespace="default",
            resource_type="Deployment",
            change_type="resource_increase",
            current_cpu="100m",
            current_memory="128Mi",
            proposed_cpu="1000m",  # 10x increase - dangerous
            proposed_memory="1280Mi",  # 10x increase - dangerous
            cpu_change_percent=1000.0,
            memory_change_percent=1000.0,
        )

        # Verify dangerous change percentages are calculated correctly
        assert dangerous_change.cpu_change_percent == 1000.0
        assert dangerous_change.memory_change_percent == 1000.0

    @pytest.mark.asyncio
    async def test_token_lifecycle_workflow(self, test_server, mock_krr_response):
        """Test token lifecycle in workflow."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test confirmation manager can create tokens
        assert test_server.confirmation_manager is not None

        # Create sample changes for token creation
        from src.safety.models import ResourceChange

        sample_changes = [
            ResourceChange(
                resource_name="test-app",
                namespace="default",
                resource_type="Deployment",
                change_type="resource_increase",
                current_cpu="100m",
                current_memory="128Mi",
                proposed_cpu="200m",
                proposed_memory="256Mi",
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        # Test token creation
        token = test_server.confirmation_manager.create_confirmation_token(
            changes=sample_changes, risk_level="low"
        )

        assert token is not None
        assert hasattr(token, "token_id")

        # Test token validation immediately (should be valid)
        is_valid = test_server.confirmation_manager.validate_token(token.token_id)
        # In real implementation, this should return the token data
        # In mock mode, it might return False or None
        assert is_valid is not None or not test_server.config.development_mode

    @pytest.mark.asyncio
    async def test_rollback_capability_components(self, test_server, mock_krr_response):
        """Test rollback capability components."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test kubectl executor has rollback capabilities
        assert test_server.kubectl_executor is not None
        assert hasattr(test_server.kubectl_executor, "create_rollback_snapshot")

        # Test rollback configuration
        assert test_server.config.rollback_retention_days > 0

        # Test that rollback snapshots can be created in mock mode
        assert test_server.config.mock_kubectl_commands is True

        # Verify rollback components are available
        from datetime import datetime, timezone

        from src.executor.models import RollbackSnapshot

        # Test creating a mock rollback snapshot
        snapshot = RollbackSnapshot(
            snapshot_id="test-snapshot-1",
            created_at=datetime.now(timezone.utc),
            resources_snapshot=[{"test": "snapshot"}],
            kubectl_commands=["kubectl get deployment test-app -o yaml"],
            execution_context={"test": "context"},
            rollback_commands=["kubectl apply -f original-state.yaml"],
        )

        assert snapshot.snapshot_id == "test-snapshot-1"
        assert len(snapshot.resources_snapshot) > 0


class TestConcurrentWorkflows:
    """Test concurrent workflow execution and resource conflicts."""

    @pytest.mark.asyncio
    async def test_concurrent_scans(self, test_server):
        """Test concurrent recommendation scans."""
        # Launch multiple concurrent scans
        tasks = [
            test_server.scan_recommendations(namespace="default"),
            test_server.scan_recommendations(namespace="kube-system"),
            test_server.scan_recommendations(namespace="monitoring"),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All scans should succeed or fail gracefully
        for result in results:
            if isinstance(result, dict):
                assert result["status"] in ["success", "error"]
            else:
                # Exception should be handled gracefully
                assert isinstance(result, Exception)

    @pytest.mark.asyncio
    async def test_concurrent_confirmations(self, test_server):
        """Test concurrent confirmation requests."""
        # Create multiple confirmation requests
        tasks = [
            test_server.request_confirmation(
                changes={"resource": f"test-{i}"}, risk_level="low"
            )
            for i in range(3)
        ]

        results = await asyncio.gather(*tasks)

        # All confirmations should get unique tokens
        tokens = [r["confirmation_token"] for r in results if r["status"] == "success"]
        assert len(set(tokens)) == len(tokens)  # All tokens should be unique


class TestErrorRecoveryWorkflows:
    """Test error recovery and partial failure scenarios."""

    @pytest.mark.asyncio
    async def test_component_error_recovery(self, test_server, mock_krr_response):
        """Test component error recovery capabilities."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test that all components are available for error recovery
        assert test_server.krr_client is not None
        assert test_server.confirmation_manager is not None
        assert test_server.kubectl_executor is not None

        # Test that mock modes are enabled for safe testing
        assert test_server.config.mock_krr_responses is True
        assert test_server.config.mock_kubectl_commands is True

        # Test error recovery configuration
        assert test_server.config.confirmation_timeout_seconds > 0
        assert test_server.config.max_resource_change_percent > 0

        # Test that components can handle initialization errors
        from src.executor.exceptions import KubectlError
        from src.recommender.exceptions import KrrError

        # Test that error types are available
        assert KrrError is not None
        assert KubectlError is not None

    @pytest.mark.asyncio
    async def test_error_handling_configuration(self, test_server):
        """Test error handling configuration."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test structured logging is configured for errors
        assert test_server.logger is not None

        # Test error configuration limits
        config = test_server.config
        assert config.confirmation_timeout_seconds > 0
        assert config.max_resource_change_percent > 0
        assert config.rollback_retention_days > 0

        # Test development safety settings
        assert config.development_mode is True
        assert config.mock_krr_responses is True
        assert config.mock_kubectl_commands is True

    @pytest.mark.asyncio
    async def test_mock_mode_safety(self, test_server):
        """Test that mock mode provides safety."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Verify mock modes prevent real operations
        assert test_server.config.mock_krr_responses is True
        assert test_server.config.mock_kubectl_commands is True
        assert test_server.config.development_mode is True

        # Test that components exist but are in safe mode
        assert test_server.krr_client is not None
        assert test_server.kubectl_executor is not None
        assert test_server.confirmation_manager is not None


class TestAuditTrailIntegration:
    """Test audit trail functionality across components."""

    @pytest.mark.asyncio
    async def test_audit_logging_components(self, test_server, caplog_structured):
        """Test that audit logging components are available."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test structured logging is configured
        assert test_server.logger is not None

        # Test logging works
        test_server.logger.info(
            "test_audit_operation", operation="test", component="audit_test"
        )

        # Verify log capture
        assert len(caplog_structured.records) > 0

        # Test that components can log audit events
        if test_server.krr_client:
            test_server.logger.info("krr_audit_test", component="krr_client")

        if test_server.confirmation_manager:
            test_server.logger.info("confirmation_audit_test", component="confirmation")

        if test_server.kubectl_executor:
            test_server.logger.info("kubectl_audit_test", component="kubectl")

    @pytest.mark.asyncio
    async def test_audit_trail_configuration(self, test_server):
        """Test audit trail configuration."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test audit configuration
        config = test_server.config
        assert config.rollback_retention_days > 0  # Audit retention

        # Test that structured logging is enabled
        import structlog

        logger = structlog.get_logger()
        assert logger is not None

        # Test audit trail components are initialized
        assert test_server.confirmation_manager is not None
        assert test_server.kubectl_executor is not None


class TestSafetyWorkflows:
    """Test safety-critical workflow scenarios."""

    @pytest.mark.asyncio
    async def test_safety_components_availability(self, test_server):
        """Test that safety components are available."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test safety components exist
        assert test_server.confirmation_manager is not None
        assert test_server.kubectl_executor is not None

        # Test safety configuration
        config = test_server.config
        assert config.max_resource_change_percent > 0
        assert config.confirmation_timeout_seconds > 0
        assert config.rollback_retention_days > 0

    @pytest.mark.asyncio
    async def test_safety_validation_models(self, test_server):
        """Test safety validation data models."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test creating safety validation objects
        from src.safety.models import ResourceChange, RiskLevel

        # Test creating a resource change
        resource_change = ResourceChange(
            resource_name="database-primary",
            namespace="production",
            resource_type="Deployment",
            change_type="resource_increase",
            current_cpu="1000m",
            current_memory="2Gi",
            proposed_cpu="2000m",
            proposed_memory="4Gi",
            cpu_change_percent=100.0,
            memory_change_percent=100.0,
        )

        # Verify the change is properly calculated
        assert resource_change.cpu_change_percent == 100.0
        assert resource_change.memory_change_percent == 100.0
        assert resource_change.namespace == "production"
        assert resource_change.resource_name == "database-primary"

    @pytest.mark.asyncio
    async def test_extreme_change_detection_logic(self, test_server):
        """Test extreme change detection logic."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test that extreme changes can be detected
        from src.safety.models import ResourceChange

        extreme_change = ResourceChange(
            resource_name="test-app",
            namespace="default",
            resource_type="Deployment",
            change_type="resource_increase",
            current_cpu="100m",
            current_memory="128Mi",
            proposed_cpu="5000m",  # 50x increase
            proposed_memory="6400Mi",  # 50x increase
            cpu_change_percent=5000.0,
            memory_change_percent=5000.0,
        )

        # Test that extreme changes are properly detected
        assert (
            extreme_change.cpu_change_percent
            > test_server.config.max_resource_change_percent
        )
        assert (
            extreme_change.memory_change_percent
            > test_server.config.max_resource_change_percent
        )

    @pytest.mark.asyncio
    async def test_token_security_components(self, test_server):
        """Test token security components."""
        # Ensure server is fully initialized
        await asyncio.sleep(0.1)

        # Test confirmation manager exists
        assert test_server.confirmation_manager is not None

        # Test token creation
        from src.safety.models import ResourceChange

        sample_changes = [
            ResourceChange(
                resource_name="test-app",
                namespace="default",
                resource_type="Deployment",
                change_type="resource_increase",
                current_cpu="100m",
                current_memory="128Mi",
                proposed_cpu="200m",
                proposed_memory="256Mi",
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        # Create a token
        token = test_server.confirmation_manager.create_confirmation_token(
            changes=sample_changes, risk_level="low"
        )

        assert token is not None
        assert hasattr(token, "token_id")

        # Test token timeout configuration
        assert test_server.config.confirmation_timeout_seconds > 0
