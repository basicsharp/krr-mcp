"""Tests for confirmation manager."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.safety.confirmation_manager import ConfirmationManager
from src.safety.models import ChangeType, ResourceChange, RiskLevel


class TestConfirmationManager:
    """Test ConfirmationManager class."""

    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = ConfirmationManager()

        assert manager.confirmation_timeout_minutes == 5
        assert manager.safety_validator is not None
        assert manager.logger is not None
        assert len(manager._confirmation_tokens) == 0
        assert len(manager._audit_log) == 0
        assert len(manager._rollback_snapshots) == 0

    def test_manager_custom_timeout(self):
        """Test manager with custom timeout."""
        manager = ConfirmationManager(confirmation_timeout_minutes=10)
        assert manager.confirmation_timeout_minutes == 10

    @pytest.mark.asyncio
    async def test_request_confirmation_simple(self):
        """Test simple confirmation request."""
        manager = ConfirmationManager()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
            )
        ]

        result = await manager.request_confirmation(changes)

        assert result["confirmation_required"] is True
        assert "confirmation_token" in result
        assert "expires_at" in result
        assert "safety_assessment" in result
        assert "confirmation_prompt" in result
        assert "changes_summary" in result

        # Verify token was stored
        token_id = result["confirmation_token"]
        assert token_id in manager._confirmation_tokens

        # Verify audit log entry was created
        assert len(manager._audit_log) == 1
        assert manager._audit_log[0].operation == "confirmation_requested"
        assert manager._audit_log[0].status == "requested"

    @pytest.mark.asyncio
    async def test_request_confirmation_with_user_context(self):
        """Test confirmation request with user context."""
        manager = ConfirmationManager()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
            )
        ]

        user_context = {"user": "test-user", "session": "session-123"}

        result = await manager.request_confirmation(changes, user_context=user_context)

        token_id = result["confirmation_token"]
        token = manager._confirmation_tokens[token_id]

        assert token.user_context == user_context
        assert manager._audit_log[0].user_context == user_context

    @pytest.mark.asyncio
    async def test_request_confirmation_custom_timeout(self):
        """Test confirmation request with custom timeout."""
        manager = ConfirmationManager()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
            )
        ]

        result = await manager.request_confirmation(changes, custom_timeout_minutes=10)

        assert result["timeout_minutes"] == 10

        token_id = result["confirmation_token"]
        token = manager._confirmation_tokens[token_id]

        # Should expire in 10 minutes
        expected_expiry = token.created_at + timedelta(minutes=10)
        assert abs((token.expires_at - expected_expiry).total_seconds()) < 1

    def test_validate_confirmation_token_valid(self):
        """Test validation of valid token."""
        manager = ConfirmationManager()

        # Create a token manually
        changes = []
        from src.safety.models import ConfirmationToken, SafetyAssessment

        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.LOW,
            total_resources_affected=0,
        )

        token = ConfirmationToken(
            changes=changes,
            safety_assessment=assessment,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        manager._confirmation_tokens[token.token_id] = token

        result = manager.validate_confirmation_token(token.token_id)

        assert result["valid"] is True
        assert "token" in result
        assert "changes" in result
        assert "safety_assessment" in result

    def test_validate_confirmation_token_not_found(self):
        """Test validation of non-existent token."""
        manager = ConfirmationManager()

        result = manager.validate_confirmation_token("non-existent-token")

        assert result["valid"] is False
        assert result["error"] == "Token not found"
        assert result["error_code"] == "TOKEN_NOT_FOUND"

    def test_validate_confirmation_token_expired(self):
        """Test validation of expired token."""
        manager = ConfirmationManager()

        # Create an expired token
        changes = []
        from src.safety.models import ConfirmationToken, SafetyAssessment

        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.LOW,
            total_resources_affected=0,
        )

        token = ConfirmationToken(
            changes=changes,
            safety_assessment=assessment,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # Expired
        )

        manager._confirmation_tokens[token.token_id] = token

        result = manager.validate_confirmation_token(token.token_id)

        assert result["valid"] is False
        assert result["error"] == "Token has expired"
        assert result["error_code"] == "TOKEN_EXPIRED"

    def test_validate_confirmation_token_already_used(self):
        """Test validation of already used token."""
        manager = ConfirmationManager()

        # Create a used token
        changes = []
        from src.safety.models import ConfirmationToken, SafetyAssessment

        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.LOW,
            total_resources_affected=0,
        )

        token = ConfirmationToken(
            changes=changes,
            safety_assessment=assessment,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        token.mark_used()  # Mark as used

        manager._confirmation_tokens[token.token_id] = token

        result = manager.validate_confirmation_token(token.token_id)

        assert result["valid"] is False
        assert result["error"] == "Token has already been used"
        assert result["error_code"] == "TOKEN_ALREADY_USED"

    def test_consume_confirmation_token_valid(self):
        """Test consuming a valid token."""
        manager = ConfirmationManager()

        # Create a valid token
        changes = []
        from src.safety.models import ConfirmationToken, SafetyAssessment

        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.LOW,
            total_resources_affected=0,
        )

        token = ConfirmationToken(
            changes=changes,
            safety_assessment=assessment,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        manager._confirmation_tokens[token.token_id] = token

        consumed_token = manager.consume_confirmation_token(token.token_id)

        assert consumed_token is not None
        assert consumed_token.used is True
        assert consumed_token.used_at is not None

        # Should create audit log entry
        approval_entries = [
            e for e in manager._audit_log if e.operation == "confirmation_consumed"
        ]
        assert len(approval_entries) == 1
        assert approval_entries[0].status == "approved"

    def test_consume_confirmation_token_invalid(self):
        """Test consuming an invalid token."""
        manager = ConfirmationManager()

        result = manager.consume_confirmation_token("invalid-token")

        assert result is None

    def test_create_rollback_snapshot(self):
        """Test creating a rollback snapshot."""
        manager = ConfirmationManager()

        manifests = [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "test-app", "namespace": "default"},
                "spec": {"replicas": 1},
            }
        ]

        rollback_commands = ["kubectl apply -f original-manifest.yaml"]
        cluster_context = {"cluster": "test-cluster", "context": "test-context"}

        snapshot_id = manager.create_rollback_snapshot(
            operation_id="op-123",
            confirmation_token_id="token-456",
            original_manifests=manifests,
            rollback_commands=rollback_commands,
            cluster_context=cluster_context,
        )

        assert snapshot_id is not None
        assert snapshot_id in manager._rollback_snapshots

        snapshot = manager._rollback_snapshots[snapshot_id]
        assert snapshot.operation_id == "op-123"
        assert snapshot.confirmation_token_id == "token-456"
        assert len(snapshot.original_manifests) == 1
        assert len(snapshot.rollback_commands) == 1
        assert len(snapshot.affected_resources) == 1
        assert snapshot.affected_resources[0]["kind"] == "Deployment"

    def test_get_rollback_snapshot_valid(self):
        """Test getting a valid rollback snapshot."""
        manager = ConfirmationManager()

        # Create a snapshot
        snapshot_id = manager.create_rollback_snapshot(
            operation_id="op-123",
            confirmation_token_id="token-456",
            original_manifests=[],
            rollback_commands=[],
            cluster_context={},
        )

        retrieved_snapshot = manager.get_rollback_snapshot(snapshot_id)

        assert retrieved_snapshot is not None
        assert retrieved_snapshot.snapshot_id == snapshot_id

    def test_get_rollback_snapshot_not_found(self):
        """Test getting a non-existent rollback snapshot."""
        manager = ConfirmationManager()

        result = manager.get_rollback_snapshot("non-existent-snapshot")

        assert result is None

    def test_get_rollback_snapshot_expired(self):
        """Test getting an expired rollback snapshot."""
        manager = ConfirmationManager()

        # Create an expired snapshot
        from src.safety.models import RollbackSnapshot

        snapshot = RollbackSnapshot(
            operation_id="op-123",
            confirmation_token_id="token-456",
            original_manifests=[],
            rollback_commands=[],
            cluster_context={},
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired
        )

        manager._rollback_snapshots[snapshot.snapshot_id] = snapshot

        result = manager.get_rollback_snapshot(snapshot.snapshot_id)

        assert result is None

    def test_log_operation_result(self):
        """Test logging operation results."""
        manager = ConfirmationManager()

        entry_id = manager.log_operation_result(
            operation="apply_recommendations",
            status="executed",
            execution_results={"resources_updated": 3},
        )

        assert entry_id is not None
        assert len(manager._audit_log) == 1

        entry = manager._audit_log[0]
        assert entry.operation == "apply_recommendations"
        assert entry.status == "executed"
        assert entry.execution_results["resources_updated"] == 3

    def test_log_operation_result_with_error(self):
        """Test logging operation results with error."""
        manager = ConfirmationManager()

        entry_id = manager.log_operation_result(
            operation="apply_recommendations",
            status="failed",
            error_message="Network timeout",
            error_details={"timeout_seconds": 30},
        )

        assert entry_id is not None

        entry = manager._audit_log[0]
        assert entry.operation == "apply_recommendations"
        assert entry.status == "failed"
        assert entry.error_message == "Network timeout"
        assert entry.error_details["timeout_seconds"] == 30

    def test_get_audit_history_default(self):
        """Test getting audit history with defaults."""
        manager = ConfirmationManager()

        # Create some audit entries
        for i in range(5):
            manager.log_operation_result(
                operation=f"operation_{i}",
                status="completed",
            )

        history = manager.get_audit_history()

        assert len(history) == 5
        # Should be sorted by timestamp (newest first)
        assert history[0]["operation"] == "operation_4"
        assert history[4]["operation"] == "operation_0"

    def test_get_audit_history_with_filters(self):
        """Test getting audit history with filters."""
        manager = ConfirmationManager()

        # Create mixed audit entries
        manager.log_operation_result(operation="apply", status="completed")
        manager.log_operation_result(operation="rollback", status="completed")
        manager.log_operation_result(operation="apply", status="failed")

        # Filter by operation
        apply_history = manager.get_audit_history(operation_filter="apply")
        assert len(apply_history) == 2
        assert all(entry["operation"] == "apply" for entry in apply_history)

        # Filter by status
        failed_history = manager.get_audit_history(status_filter="failed")
        assert len(failed_history) == 1
        assert failed_history[0]["status"] == "failed"

    def test_get_audit_history_with_limit(self):
        """Test getting audit history with limit."""
        manager = ConfirmationManager()

        # Create many audit entries
        for i in range(10):
            manager.log_operation_result(operation=f"operation_{i}", status="completed")

        history = manager.get_audit_history(limit=3)

        assert len(history) == 3

    def test_cleanup_expired_tokens(self):
        """Test cleanup of expired tokens."""
        manager = ConfirmationManager()

        # Create expired and valid tokens
        from src.safety.models import ConfirmationToken, SafetyAssessment

        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.LOW,
            total_resources_affected=0,
        )

        # Expired token
        expired_token = ConfirmationToken(
            changes=[],
            safety_assessment=assessment,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        manager._confirmation_tokens[expired_token.token_id] = expired_token

        # Valid token
        valid_token = ConfirmationToken(
            changes=[],
            safety_assessment=assessment,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        manager._confirmation_tokens[valid_token.token_id] = valid_token

        assert len(manager._confirmation_tokens) == 2

        cleaned_count = manager.cleanup_expired_tokens()

        assert cleaned_count == 1
        assert len(manager._confirmation_tokens) == 1
        assert valid_token.token_id in manager._confirmation_tokens
        assert expired_token.token_id not in manager._confirmation_tokens

    def test_cleanup_expired_snapshots(self):
        """Test cleanup of expired snapshots."""
        manager = ConfirmationManager()

        # Create expired and valid snapshots
        from src.safety.models import RollbackSnapshot

        # Expired snapshot
        expired_snapshot = RollbackSnapshot(
            operation_id="op-1",
            confirmation_token_id="token-1",
            original_manifests=[],
            rollback_commands=[],
            cluster_context={},
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        manager._rollback_snapshots[expired_snapshot.snapshot_id] = expired_snapshot

        # Valid snapshot
        valid_snapshot = RollbackSnapshot(
            operation_id="op-2",
            confirmation_token_id="token-2",
            original_manifests=[],
            rollback_commands=[],
            cluster_context={},
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        manager._rollback_snapshots[valid_snapshot.snapshot_id] = valid_snapshot

        assert len(manager._rollback_snapshots) == 2

        cleaned_count = manager.cleanup_expired_snapshots()

        assert cleaned_count == 1
        assert len(manager._rollback_snapshots) == 1
        assert valid_snapshot.snapshot_id in manager._rollback_snapshots
        assert expired_snapshot.snapshot_id not in manager._rollback_snapshots

    def test_generate_confirmation_prompt(self):
        """Test confirmation prompt generation."""
        manager = ConfirmationManager()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
            )
        ]

        from src.safety.models import SafetyAssessment, SafetyWarning

        warnings = [
            SafetyWarning(
                level=RiskLevel.MEDIUM,
                message="Test warning",
                recommendation="Test recommendation",
                affected_object="Deployment/test-app",
            )
        ]

        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.MEDIUM,
            total_resources_affected=1,
            warnings=warnings,
        )

        prompt = manager._generate_confirmation_prompt(changes, assessment)

        assert "KUBERNETES RESOURCE MODIFICATION CONFIRMATION" in prompt
        assert "Risk Level: MEDIUM" in prompt
        assert "Resources Affected: 1" in prompt
        assert "test-app" in prompt
        assert "SAFETY WARNINGS" in prompt
        assert "Test warning" in prompt

    def test_generate_changes_summary(self):
        """Test changes summary generation."""
        manager = ConfirmationManager()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="app1",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
            ),
            ResourceChange(
                object_kind="StatefulSet",
                object_name="app2",
                namespace="prod",
                change_type=ChangeType.RESOURCE_DECREASE,
                current_values={"cpu": "500m", "memory": "512Mi"},
                proposed_values={"cpu": "300m", "memory": "256Mi"},
            ),
        ]

        # Calculate impact for the changes
        for change in changes:
            change.calculate_impact()

        summary = manager._generate_changes_summary(changes)

        assert summary["total_changes"] == 2
        assert summary["by_kind"]["Deployment"] == 1
        assert summary["by_kind"]["StatefulSet"] == 1
        assert summary["by_namespace"]["default"] == 1
        assert summary["by_namespace"]["prod"] == 1
        assert summary["by_change_type"]["resource_increase"] == 1
        assert summary["by_change_type"]["resource_decrease"] == 1
        assert summary["resource_impact"]["cpu_increases"] == 1
        assert summary["resource_impact"]["cpu_decreases"] == 1
        assert summary["resource_impact"]["memory_increases"] == 1
        assert summary["resource_impact"]["memory_decreases"] == 1
