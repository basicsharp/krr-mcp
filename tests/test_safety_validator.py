"""Tests for safety validator."""

import pytest

from src.safety.models import ChangeType, ResourceChange, RiskLevel
from src.safety.validator import SafetyConfig, SafetyValidator


class TestSafetyConfig:
    """Test SafetyConfig class."""

    def test_default_configuration(self):
        """Test default safety configuration."""
        config = SafetyConfig()

        assert config.MAX_CPU_INCREASE_PERCENT == 500
        assert config.MAX_MEMORY_INCREASE_PERCENT == 500
        assert config.HIGH_IMPACT_THRESHOLD_PERCENT == 100
        assert len(config.CRITICAL_WORKLOAD_PATTERNS) > 0
        assert len(config.PRODUCTION_NAMESPACE_PATTERNS) > 0


class TestSafetyValidator:
    """Test SafetyValidator class."""

    def test_validator_initialization(self):
        """Test validator initialization."""
        validator = SafetyValidator()
        assert validator.config is not None
        assert validator.logger is not None

    def test_validator_with_custom_config(self):
        """Test validator with custom configuration."""
        config = SafetyConfig()
        config.MAX_CPU_INCREASE_PERCENT = 200

        validator = SafetyValidator(config)
        assert validator.config.MAX_CPU_INCREASE_PERCENT == 200

    def test_validate_empty_changes(self):
        """Test validation with empty changes list."""
        validator = SafetyValidator()
        assessment = validator.validate_changes([])

        assert assessment.overall_risk_level == RiskLevel.LOW
        assert assessment.total_resources_affected == 0
        assert len(assessment.warnings) == 0

    def test_validate_safe_changes(self):
        """Test validation with safe changes."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="safe-app",
                namespace="dev",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "150m", "memory": "192Mi"},
            )
        ]

        assessment = validator.validate_changes(changes)

        assert assessment.overall_risk_level == RiskLevel.LOW
        assert assessment.total_resources_affected == 1
        assert assessment.high_impact_changes == 0
        assert assessment.critical_workloads_affected == 0

    def test_validate_high_cpu_increase(self):
        """Test validation with high CPU increase."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "700m", "memory": "128Mi"},  # 600% increase
            )
        ]

        assessment = validator.validate_changes(changes)

        assert assessment.overall_risk_level == RiskLevel.CRITICAL
        assert assessment.total_resources_affected == 1
        assert len(assessment.warnings) > 0

        # Should have a warning about exceeding limits
        cpu_warnings = [w for w in assessment.warnings if "CPU increase" in w.message]
        assert len(cpu_warnings) > 0
        assert cpu_warnings[0].level == RiskLevel.CRITICAL

    def test_validate_high_memory_increase(self):
        """Test validation with high memory increase."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "100m", "memory": "1Gi"},  # ~700% increase
            )
        ]

        assessment = validator.validate_changes(changes)

        assert assessment.overall_risk_level == RiskLevel.CRITICAL

        # Should have a warning about exceeding limits
        memory_warnings = [
            w for w in assessment.warnings if "Memory increase" in w.message
        ]
        assert len(memory_warnings) > 0
        assert memory_warnings[0].level == RiskLevel.CRITICAL

    def test_validate_critical_workload(self):
        """Test validation with critical workload names."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="prod-database",  # Matches critical pattern
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
            )
        ]

        assessment = validator.validate_changes(changes)

        assert assessment.overall_risk_level == RiskLevel.HIGH
        assert assessment.critical_workloads_affected == 1

        # Should have a warning about critical workload
        critical_warnings = [
            w for w in assessment.warnings if "critical workload" in w.message
        ]
        assert len(critical_warnings) > 0
        assert critical_warnings[0].level == RiskLevel.HIGH

    def test_validate_production_namespace(self):
        """Test validation with production namespace."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="production",  # Matches production pattern
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
            )
        ]

        assessment = validator.validate_changes(changes)

        assert assessment.overall_risk_level == RiskLevel.HIGH
        assert "production" in assessment.production_namespaces_affected

        # Should have a warning about production namespace
        prod_warnings = [
            w for w in assessment.warnings if "production namespace" in w.message
        ]
        assert len(prod_warnings) > 0
        assert prod_warnings[0].level == RiskLevel.HIGH

    def test_validate_extreme_cpu_increase(self):
        """Test validation with extreme CPU increase."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "1200m", "memory": "128Mi"},  # 1100% increase
            )
        ]

        assessment = validator.validate_changes(changes)

        assert assessment.overall_risk_level == RiskLevel.CRITICAL

        # Should have warnings about both limit violation and extreme change
        limit_warnings = [
            w
            for w in assessment.warnings
            if "CPU increase" in w.message and "exceeds maximum" in w.message
        ]
        extreme_warnings = [
            w for w in assessment.warnings if "Extreme resource changes" in w.message
        ]

        assert len(limit_warnings) > 0
        assert len(extreme_warnings) > 0

    def test_validate_extreme_decrease(self):
        """Test validation with extreme resource decrease."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_DECREASE,
                current_values={"cpu": "1000m", "memory": "1Gi"},
                proposed_values={"cpu": "50m", "memory": "64Mi"},  # >90% decrease
            )
        ]

        assessment = validator.validate_changes(changes)

        # Should have a warning about extreme changes
        extreme_warnings = [
            w for w in assessment.warnings if "Extreme resource changes" in w.message
        ]
        assert len(extreme_warnings) > 0
        assert extreme_warnings[0].level == RiskLevel.CRITICAL

    def test_validate_many_simultaneous_changes(self):
        """Test validation with many simultaneous changes."""
        validator = SafetyValidator()

        # Create 25 changes (above the threshold)
        changes = []
        for i in range(25):
            changes.append(
                ResourceChange(
                    object_kind="Deployment",
                    object_name=f"test-app-{i}",
                    namespace="default",
                    change_type=ChangeType.RESOURCE_INCREASE,
                    current_values={"cpu": "100m", "memory": "128Mi"},
                    proposed_values={"cpu": "150m", "memory": "192Mi"},
                )
            )

        assessment = validator.validate_changes(changes)

        # Should have a warning about large number of changes
        bulk_warnings = [
            w
            for w in assessment.warnings
            if "Large number of simultaneous changes" in w.message
        ]
        assert len(bulk_warnings) > 0
        assert bulk_warnings[0].level == RiskLevel.MEDIUM

    def test_validate_multiple_production_namespaces(self):
        """Test validation with changes across multiple production namespaces."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="app1",
                namespace="prod-web",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
            ),
            ResourceChange(
                object_kind="Deployment",
                object_name="app2",
                namespace="prod-api",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
            ),
            ResourceChange(
                object_kind="Deployment",
                object_name="app3",
                namespace="prod-db",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
            ),
            ResourceChange(
                object_kind="Deployment",
                object_name="app4",
                namespace="production",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
            ),
        ]

        assessment = validator.validate_changes(changes)

        # Should identify all production namespaces
        assert len(assessment.production_namespaces_affected) == 4

        # Should have a warning about multiple production namespaces
        multi_prod_warnings = [
            w
            for w in assessment.warnings
            if "multiple production namespaces" in w.message
        ]
        assert len(multi_prod_warnings) > 0
        assert multi_prod_warnings[0].level == RiskLevel.HIGH

    def test_gradual_rollout_requirements(self):
        """Test conditions that require gradual rollout."""
        validator = SafetyValidator()

        # Create changes that should trigger gradual rollout
        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="critical-app",
                namespace="production",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "400m", "memory": "512Mi"},  # Large change
            )
        ]

        assessment = validator.validate_changes(changes)

        assert assessment.requires_gradual_rollout

    def test_monitoring_requirements(self):
        """Test conditions that require enhanced monitoring."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="production",  # Production namespace
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
            )
        ]

        assessment = validator.validate_changes(changes)

        assert assessment.requires_monitoring

    def test_backup_requirements(self):
        """Test conditions that require backup."""
        validator = SafetyValidator()

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="production",  # Production namespace
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
            )
        ]

        assessment = validator.validate_changes(changes)

        assert assessment.requires_backup

    def test_high_impact_change_detection(self):
        """Test detection of high impact changes."""
        validator = SafetyValidator()

        # Create a change with >100% increase (high impact threshold)
        change = ResourceChange(
            object_kind="Deployment",
            object_name="test-app",
            namespace="default",
            change_type=ChangeType.RESOURCE_INCREASE,
            current_values={"cpu": "100m", "memory": "128Mi"},
            proposed_values={"cpu": "250m", "memory": "256Mi"},  # 150% CPU, 100% memory
        )
        change.calculate_impact()

        assert validator._is_high_impact_change(change)

    def test_critical_workload_patterns(self):
        """Test critical workload pattern matching."""
        validator = SafetyValidator()

        critical_names = [
            "prod-database",
            "production-web",
            "critical-service",
            "redis-cluster",
            "etcd-server",
            "ingress-controller",
        ]

        for name in critical_names:
            changes = [
                ResourceChange(
                    object_kind="Deployment",
                    object_name=name,
                    namespace="default",
                    change_type=ChangeType.RESOURCE_INCREASE,
                    current_values={"cpu": "100m"},
                    proposed_values={"cpu": "200m"},
                )
            ]

            assessment = validator.validate_changes(changes)
            assert (
                assessment.critical_workloads_affected >= 1
            ), f"Failed to detect critical workload: {name}"

    def test_production_namespace_patterns(self):
        """Test production namespace pattern matching."""
        validator = SafetyValidator()

        production_namespaces = [
            "prod",
            "production",
            "web-prod",
            "api-production",
            "default",
        ]

        for namespace in production_namespaces:
            changes = [
                ResourceChange(
                    object_kind="Deployment",
                    object_name="test-app",
                    namespace=namespace,
                    change_type=ChangeType.RESOURCE_INCREASE,
                    current_values={"cpu": "100m"},
                    proposed_values={"cpu": "200m"},
                )
            ]

            assessment = validator.validate_changes(changes)
            assert (
                namespace in assessment.production_namespaces_affected
            ), f"Failed to detect production namespace: {namespace}"
