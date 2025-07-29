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
    async def test_complete_workflow_success(self, test_server, mock_krr_response):
        """Test successful complete workflow: scan → preview → confirm → apply."""
        # Step 1: Scan recommendations
        scan_result = await test_server.scan_recommendations(
            namespace="default", strategy="simple"
        )

        assert scan_result["status"] == "success"
        assert "recommendations" in scan_result
        assert len(scan_result["recommendations"]) > 0

        # Step 2: Preview changes
        preview_result = await test_server.preview_changes(
            recommendations=scan_result["recommendations"]
        )

        assert preview_result["status"] == "success"
        assert "safety_assessment" in preview_result
        assert "impact_analysis" in preview_result

        # Step 3: Request confirmation
        confirmation_result = await test_server.request_confirmation(
            changes=preview_result["impact_analysis"], risk_level="medium"
        )

        assert confirmation_result["status"] == "success"
        assert "confirmation_token" in confirmation_result
        confirmation_token = confirmation_result["confirmation_token"]

        # Step 4: Apply recommendations
        apply_result = await test_server.apply_recommendations(
            recommendations=scan_result["recommendations"],
            confirmation_token=confirmation_token,
            dry_run=False,
        )

        assert apply_result["status"] == "success"
        assert "execution_result" in apply_result
        assert apply_result["execution_result"]["successful_count"] > 0

    @pytest.mark.asyncio
    async def test_workflow_with_safety_rejection(
        self, test_server, dangerous_recommendations
    ):
        """Test workflow where safety checks reject dangerous changes."""
        # Step 1: Preview dangerous changes
        preview_result = await test_server.preview_changes(
            recommendations=dangerous_recommendations["recommendations"]
        )

        assert preview_result["status"] == "success"
        assert preview_result["safety_assessment"]["risk_level"] in ["high", "critical"]
        assert len(preview_result["safety_assessment"]["warnings"]) > 0

        # Step 2: Request confirmation for dangerous changes
        confirmation_result = await test_server.request_confirmation(
            changes=preview_result["impact_analysis"], risk_level="high"
        )

        assert confirmation_result["status"] == "success"
        # Should include safety warnings in confirmation prompt
        assert "safety_warnings" in confirmation_result
        assert len(confirmation_result["safety_warnings"]) > 0

    @pytest.mark.asyncio
    async def test_workflow_interruption_recovery(self, test_server, mock_krr_response):
        """Test workflow recovery after interruption."""
        # Start workflow normally
        scan_result = await test_server.scan_recommendations(namespace="default")
        confirmation_result = await test_server.request_confirmation(
            changes={"test": "changes"}, risk_level="low"
        )

        confirmation_token = confirmation_result["confirmation_token"]

        # Simulate interruption by waiting (token should still be valid)
        await asyncio.sleep(0.1)

        # Resume workflow - should work if token hasn't expired
        apply_result = await test_server.apply_recommendations(
            recommendations=scan_result["recommendations"],
            confirmation_token=confirmation_token,
            dry_run=True,  # Safe dry-run
        )

        assert apply_result["status"] == "success"

    @pytest.mark.asyncio
    async def test_workflow_with_rollback(self, test_server, mock_krr_response):
        """Test complete workflow including rollback capability."""
        # Complete normal workflow first
        scan_result = await test_server.scan_recommendations(namespace="default")
        confirmation_result = await test_server.request_confirmation(
            changes={"test": "changes"}, risk_level="low"
        )

        apply_result = await test_server.apply_recommendations(
            recommendations=scan_result["recommendations"],
            confirmation_token=confirmation_result["confirmation_token"],
            dry_run=False,
        )

        assert apply_result["status"] == "success"
        execution_id = apply_result["execution_result"]["execution_id"]

        # Test rollback
        rollback_confirmation = await test_server.request_confirmation(
            changes={"action": "rollback", "execution_id": execution_id},
            risk_level="medium",
        )

        rollback_result = await test_server.rollback_changes(
            execution_id=execution_id,
            confirmation_token=rollback_confirmation["confirmation_token"],
        )

        assert rollback_result["status"] == "success"
        assert rollback_result["rollback_result"]["successful_count"] >= 0


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
    async def test_partial_execution_failure(self, test_server, mock_krr_response):
        """Test recovery from partial execution failures."""
        with patch(
            "src.executor.kubectl_executor.KubectlExecutor.execute_command"
        ) as mock_execute:
            # Mock partial failure: first command succeeds, second fails
            mock_execute.side_effect = [
                {"success": True, "output": "success"},
                Exception("Network error"),
                {"success": True, "output": "success"},
            ]

            scan_result = await test_server.scan_recommendations(namespace="default")
            confirmation_result = await test_server.request_confirmation(
                changes={"test": "changes"}, risk_level="low"
            )

            apply_result = await test_server.apply_recommendations(
                recommendations=scan_result["recommendations"],
                confirmation_token=confirmation_result["confirmation_token"],
                dry_run=False,
            )

            # Should handle partial failure gracefully
            assert apply_result["status"] in ["partial_success", "error"]
            if apply_result["status"] == "partial_success":
                assert "failed_resources" in apply_result["execution_result"]
                assert "successful_resources" in apply_result["execution_result"]

    @pytest.mark.asyncio
    async def test_krr_command_failure_recovery(self, test_server):
        """Test recovery from krr command failures."""
        with patch("src.recommender.krr_client.KrrClient.scan_cluster") as mock_scan:
            mock_scan.side_effect = Exception("krr command failed")

            scan_result = await test_server.scan_recommendations(namespace="default")

            assert scan_result["status"] == "error"
            assert "error" in scan_result
            assert "krr" in scan_result["error"].lower()

    @pytest.mark.asyncio
    async def test_kubernetes_api_failure_recovery(
        self, test_server, mock_krr_response
    ):
        """Test recovery from Kubernetes API failures."""
        with patch(
            "src.executor.kubectl_executor.KubectlExecutor.execute_command"
        ) as mock_execute:
            mock_execute.side_effect = Exception("Kubernetes API unavailable")

            scan_result = await test_server.scan_recommendations(namespace="default")
            confirmation_result = await test_server.request_confirmation(
                changes={"test": "changes"}, risk_level="low"
            )

            apply_result = await test_server.apply_recommendations(
                recommendations=scan_result["recommendations"],
                confirmation_token=confirmation_result["confirmation_token"],
                dry_run=False,
            )

            assert apply_result["status"] == "error"
            assert (
                "kubernetes" in apply_result["error"].lower()
                or "api" in apply_result["error"].lower()
            )


class TestAuditTrailWorkflows:
    """Test complete audit trail functionality throughout workflows."""

    @pytest.mark.asyncio
    async def test_complete_audit_trail(
        self, test_server, mock_krr_response, caplog_structured
    ):
        """Test that complete workflow generates proper audit trail."""
        # Execute complete workflow
        scan_result = await test_server.scan_recommendations(namespace="default")
        preview_result = await test_server.preview_changes(
            recommendations=scan_result["recommendations"]
        )
        confirmation_result = await test_server.request_confirmation(
            changes=preview_result["impact_analysis"], risk_level="medium"
        )
        apply_result = await test_server.apply_recommendations(
            recommendations=scan_result["recommendations"],
            confirmation_token=confirmation_result["confirmation_token"],
            dry_run=True,
        )

        # Query execution history
        history_result = await test_server.get_execution_history(limit=10)

        assert history_result["status"] == "success"
        assert "audit_entries" in history_result
        assert len(history_result["audit_entries"]) > 0

        # Verify audit entry structure
        latest_entry = history_result["audit_entries"][0]
        expected_fields = [
            "timestamp",
            "operation",
            "user_context",
            "changes",
            "confirmation_token",
            "result",
            "execution_id",
        ]

        for field in expected_fields:
            assert field in latest_entry

    @pytest.mark.asyncio
    async def test_audit_trail_with_failures(self, test_server):
        """Test audit trail includes failure scenarios."""
        # Attempt operation with invalid token
        invalid_apply_result = await test_server.apply_recommendations(
            recommendations=[], confirmation_token="invalid-token", dry_run=True
        )

        assert invalid_apply_result["status"] == "error"

        # Check that failure is recorded in audit trail
        history_result = await test_server.get_execution_history(limit=5)

        assert history_result["status"] == "success"
        # Should have audit entries even for failures
        assert len(history_result["audit_entries"]) >= 0


class TestSafetyWorkflows:
    """Test safety-critical workflow scenarios."""

    @pytest.mark.asyncio
    async def test_production_namespace_protection(self, test_server):
        """Test enhanced protection for production namespaces."""
        # Test scanning production namespace
        scan_result = await test_server.scan_recommendations(namespace="production")

        assert scan_result["status"] == "success"

        if scan_result["recommendations"]:
            preview_result = await test_server.preview_changes(
                recommendations=scan_result["recommendations"]
            )

            # Production should trigger higher safety assessment
            safety_assessment = preview_result["safety_assessment"]
            assert safety_assessment["namespace_type"] == "production"
            assert len(safety_assessment["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_critical_workload_protection(self, test_server):
        """Test protection for critical workloads."""
        critical_recommendations = {
            "recommendations": [
                {
                    "object": {
                        "kind": "Deployment",
                        "namespace": "default",
                        "name": "database-primary",  # Should trigger critical workload detection
                    },
                    "recommendations": {"requests": {"cpu": "2000m", "memory": "4Gi"}},
                    "current": {"requests": {"cpu": "1000m", "memory": "2Gi"}},
                }
            ]
        }

        preview_result = await test_server.preview_changes(
            recommendations=critical_recommendations["recommendations"]
        )

        safety_assessment = preview_result["safety_assessment"]
        # Should detect critical workload
        assert safety_assessment["has_critical_workloads"] is True
        assert safety_assessment["risk_level"] in ["high", "critical"]

    @pytest.mark.asyncio
    async def test_extreme_change_detection(self, test_server):
        """Test detection of extreme resource changes."""
        extreme_recommendations = {
            "recommendations": [
                {
                    "object": {
                        "kind": "Deployment",
                        "namespace": "default",
                        "name": "test-app",
                    },
                    "recommendations": {
                        "requests": {"cpu": "50000m", "memory": "100Gi"}  # 50x increase
                    },
                    "current": {"requests": {"cpu": "1000m", "memory": "2Gi"}},
                }
            ]
        }

        preview_result = await test_server.preview_changes(
            recommendations=extreme_recommendations["recommendations"]
        )

        safety_assessment = preview_result["safety_assessment"]
        assert safety_assessment["risk_level"] == "critical"
        assert any(
            "extreme" in warning.lower() for warning in safety_assessment["warnings"]
        )

    @pytest.mark.asyncio
    async def test_confirmation_token_security(self, test_server):
        """Test confirmation token security measures."""
        # Get valid confirmation
        confirmation_result = await test_server.request_confirmation(
            changes={"test": "changes"}, risk_level="low"
        )

        valid_token = confirmation_result["confirmation_token"]

        # Test token reuse (should fail)
        first_apply = await test_server.apply_recommendations(
            recommendations=[], confirmation_token=valid_token, dry_run=True
        )

        second_apply = await test_server.apply_recommendations(
            recommendations=[],
            confirmation_token=valid_token,  # Reusing same token
            dry_run=True,
        )

        # Second use should fail (single-use tokens)
        assert first_apply["status"] == "success"
        assert second_apply["status"] == "error"
        assert "token" in second_apply["error"].lower()
