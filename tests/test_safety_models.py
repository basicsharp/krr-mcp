"""Tests for safety models."""

from datetime import datetime, timedelta, timezone

from src.safety.models import (
    AuditLogEntry,
    ChangeType,
    ConfirmationToken,
    ResourceChange,
    RiskLevel,
    RollbackSnapshot,
    SafetyAssessment,
    SafetyWarning,
)


class TestResourceChange:
    """Test ResourceChange model."""

    def test_resource_change_creation(self):
        """Test basic resource change creation."""
        change = ResourceChange(
            object_kind="Deployment",
            object_name="test-app",
            namespace="default",
            change_type=ChangeType.RESOURCE_INCREASE,
            current_values={"cpu": "100m", "memory": "128Mi"},
            proposed_values={"cpu": "200m", "memory": "256Mi"},
        )

        assert change.object_kind == "Deployment"
        assert change.object_name == "test-app"
        assert change.namespace == "default"
        assert change.change_type == ChangeType.RESOURCE_INCREASE

    def test_cpu_parsing_millicores(self):
        """Test CPU value parsing for millicores."""
        change = ResourceChange(
            object_kind="Deployment",
            object_name="test-app",
            namespace="default",
            change_type=ChangeType.RESOURCE_INCREASE,
            current_values={},
            proposed_values={},
        )

        assert change._parse_cpu_value("100m") == 100.0
        assert change._parse_cpu_value("1500m") == 1500.0
        assert change._parse_cpu_value(None) is None

    def test_cpu_parsing_cores(self):
        """Test CPU value parsing for cores."""
        change = ResourceChange(
            object_kind="Deployment",
            object_name="test-app",
            namespace="default",
            change_type=ChangeType.RESOURCE_INCREASE,
            current_values={},
            proposed_values={},
        )

        assert change._parse_cpu_value("1") == 1000.0
        assert change._parse_cpu_value("0.5") == 500.0
        assert change._parse_cpu_value("2.5") == 2500.0

    def test_memory_parsing(self):
        """Test memory value parsing."""
        change = ResourceChange(
            object_kind="Deployment",
            object_name="test-app",
            namespace="default",
            change_type=ChangeType.RESOURCE_INCREASE,
            current_values={},
            proposed_values={},
        )

        assert change._parse_memory_value("128Mi") == 128 * 1024**2
        assert change._parse_memory_value("1Gi") == 1024**3
        assert change._parse_memory_value("512Ki") == 512 * 1024
        assert change._parse_memory_value(None) is None

    def test_impact_calculation(self):
        """Test impact calculation."""
        change = ResourceChange(
            object_kind="Deployment",
            object_name="test-app",
            namespace="default",
            change_type=ChangeType.RESOURCE_INCREASE,
            current_values={"cpu": "100m", "memory": "128Mi"},
            proposed_values={"cpu": "300m", "memory": "256Mi"},
        )

        change.calculate_impact()

        assert change.cpu_change_percent == 200.0  # 100m -> 300m = 200% increase
        assert change.memory_change_percent == 100.0  # 128Mi -> 256Mi = 100% increase


class TestSafetyWarning:
    """Test SafetyWarning model."""

    def test_safety_warning_creation(self):
        """Test safety warning creation."""
        warning = SafetyWarning(
            level=RiskLevel.HIGH,
            message="High resource increase detected",
            recommendation="Consider gradual rollout",
            affected_object="Deployment/test-app",
            change_details={"cpu_change_percent": 200.0},
        )

        assert warning.level == RiskLevel.HIGH
        assert warning.message == "High resource increase detected"
        assert warning.recommendation == "Consider gradual rollout"
        assert warning.affected_object == "Deployment/test-app"
        assert warning.change_details["cpu_change_percent"] == 200.0


class TestSafetyAssessment:
    """Test SafetyAssessment model."""

    def test_safety_assessment_creation(self):
        """Test safety assessment creation."""
        warnings = [
            SafetyWarning(
                level=RiskLevel.MEDIUM,
                message="Test warning",
                recommendation="Test recommendation",
                affected_object="test-object",
            )
        ]

        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.MEDIUM,
            total_resources_affected=3,
            warnings=warnings,
            high_impact_changes=1,
            critical_workloads_affected=0,
            production_namespaces_affected=["production"],
        )

        assert assessment.overall_risk_level == RiskLevel.MEDIUM
        assert assessment.total_resources_affected == 3
        assert len(assessment.warnings) == 1
        assert assessment.high_impact_changes == 1
        assert "production" in assessment.production_namespaces_affected


class TestConfirmationToken:
    """Test ConfirmationToken model."""

    def test_confirmation_token_creation(self):
        """Test confirmation token creation."""
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

        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.LOW,
            total_resources_affected=1,
        )

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        token = ConfirmationToken(
            expires_at=expires_at,
            changes=changes,
            safety_assessment=assessment,
        )

        assert token.token_id is not None
        assert token.secret is not None
        assert len(token.changes) == 1
        assert token.safety_assessment.overall_risk_level == RiskLevel.LOW
        assert not token.used
        assert token.used_at is None

    def test_token_expiration_default(self):
        """Test token expiration default setting."""
        changes = []
        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.LOW,
            total_resources_affected=0,
        )

        token = ConfirmationToken(
            changes=changes,
            safety_assessment=assessment,
        )

        # Should have default 5-minute expiration
        expected_expiry = token.created_at + timedelta(minutes=5)
        assert abs((token.expires_at - expected_expiry).total_seconds()) < 1

    def test_token_validation(self):
        """Test token validation methods."""
        changes = []
        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.LOW,
            total_resources_affected=0,
        )

        # Create non-expired token
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        token = ConfirmationToken(
            expires_at=expires_at,
            changes=changes,
            safety_assessment=assessment,
        )

        assert token.is_valid()
        assert not token.is_expired()

        # Mark as used
        token.mark_used()
        assert token.used
        assert token.used_at is not None
        assert not token.is_valid()

    def test_expired_token(self):
        """Test expired token validation."""
        changes = []
        assessment = SafetyAssessment(
            overall_risk_level=RiskLevel.LOW,
            total_resources_affected=0,
        )

        # Create expired token
        expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        token = ConfirmationToken(
            expires_at=expires_at,
            changes=changes,
            safety_assessment=assessment,
        )

        assert token.is_expired()
        assert not token.is_valid()


class TestAuditLogEntry:
    """Test AuditLogEntry model."""

    def test_audit_log_creation(self):
        """Test audit log entry creation."""
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

        entry = AuditLogEntry(
            operation="apply_recommendations",
            status="executed",
            user_context={"user": "test-user"},
            cluster_context={"cluster": "test-cluster"},
            changes=changes,
            confirmation_token_id="test-token-123",
        )

        assert entry.entry_id is not None
        assert entry.operation == "apply_recommendations"
        assert entry.status == "executed"
        assert entry.user_context["user"] == "test-user"
        assert entry.cluster_context["cluster"] == "test-cluster"
        assert len(entry.changes) == 1
        assert entry.confirmation_token_id == "test-token-123"

    def test_audit_log_with_error(self):
        """Test audit log entry with error information."""
        entry = AuditLogEntry(
            operation="apply_recommendations",
            status="failed",
            error_message="Network timeout",
            error_details={"timeout_seconds": 30, "retry_count": 3},
        )

        assert entry.status == "failed"
        assert entry.error_message == "Network timeout"
        assert entry.error_details["timeout_seconds"] == 30
        assert entry.error_details["retry_count"] == 3


class TestRollbackSnapshot:
    """Test RollbackSnapshot model."""

    def test_rollback_snapshot_creation(self):
        """Test rollback snapshot creation."""
        manifests = [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "test-app", "namespace": "default"},
            }
        ]

        rollback_commands = [
            "kubectl apply -f original-manifest.yaml",
        ]

        snapshot = RollbackSnapshot(
            operation_id="op-123",
            confirmation_token_id="token-456",
            original_manifests=manifests,
            rollback_commands=rollback_commands,
            cluster_context={"cluster": "test-cluster"},
        )

        assert snapshot.snapshot_id is not None
        assert snapshot.operation_id == "op-123"
        assert snapshot.confirmation_token_id == "token-456"
        assert len(snapshot.original_manifests) == 1
        assert len(snapshot.rollback_commands) == 1
        assert len(snapshot.affected_resources) == 1
        assert snapshot.affected_resources[0]["kind"] == "Deployment"
        assert snapshot.affected_resources[0]["name"] == "test-app"

    def test_rollback_snapshot_expiration(self):
        """Test rollback snapshot expiration."""
        snapshot = RollbackSnapshot(
            operation_id="op-123",
            confirmation_token_id="token-456",
            original_manifests=[],
            rollback_commands=[],
            cluster_context={},
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        assert snapshot.is_expired()

    def test_rollback_snapshot_default_expiration(self):
        """Test rollback snapshot default expiration."""
        snapshot = RollbackSnapshot(
            operation_id="op-123",
            confirmation_token_id="token-456",
            original_manifests=[],
            rollback_commands=[],
            cluster_context={},
        )

        # Should have default 7-day expiration
        expected_expiry = snapshot.created_at + timedelta(days=7)
        assert abs((snapshot.expires_at - expected_expiry).total_seconds()) < 1
        assert not snapshot.is_expired()
