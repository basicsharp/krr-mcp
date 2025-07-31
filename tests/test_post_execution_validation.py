"""Tests for post-execution validation functionality."""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from src.executor.kubectl_executor import KubectlExecutor
from src.executor.models import (
    ExecutionMode,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTransaction,
    KubectlCommand,
)
from src.executor.post_execution_validator import (
    PostExecutionValidator,
    ValidationError,
    ValidationReport,
    ValidationResult,
)
from src.safety.confirmation_manager import ConfirmationManager
from src.safety.models import ChangeType, ResourceChange


class TestPostExecutionValidator:
    """Test post-execution validation functionality."""

    @pytest.fixture
    def validator(self) -> PostExecutionValidator:
        """Create a post-execution validator with mock commands."""
        return PostExecutionValidator(
            kubeconfig_path="~/.kube/config",
            kubernetes_context="test-context",
            mock_commands=True,
            validation_timeout=60,
            readiness_wait_time=10,
        )

    @pytest.fixture
    def sample_transaction(self) -> ExecutionTransaction:
        """Create a sample executed transaction."""
        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="test-app",
            namespace="default",
            kubectl_args=["patch", "deployment", "test-app", "--namespace", "default"],
        )

        result = ExecutionResult(
            command_id=command.command_id,
            status=ExecutionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_seconds=1.0,
            exit_code=0,
            stdout="deployment.apps/test-app patched",
            affected_resources=[
                {
                    "kind": "Deployment",
                    "name": "test-app",
                    "namespace": "default",
                }
            ],
        )

        transaction = ExecutionTransaction(
            confirmation_token_id="test-token-123",
            commands=[command],
            execution_mode=ExecutionMode.SINGLE,
            dry_run=False,
            command_results=[result],
            overall_status=ExecutionStatus.COMPLETED,
            commands_completed=1,
            commands_failed=0,
        )

        return transaction

    @pytest.fixture
    def sample_resource_changes(self) -> List[ResourceChange]:
        """Create sample resource changes."""
        return [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
                estimated_cost_impact=10.0,
            )
        ]

    @pytest.mark.asyncio
    async def test_validation_report_creation(self) -> None:
        """Test validation report creation and completion."""
        report = ValidationReport("test-transaction-123")

        assert report.transaction_id == "test-transaction-123"
        assert report.started_at is not None
        assert report.completed_at is None
        assert report.overall_success is True
        assert len(report.results) == 0

        # Add a successful result
        success_result = ValidationResult(
            validation_type="resource_changes",
            resource_type="Deployment",
            resource_name="test-app",
            namespace="default",
            success=True,
            message="Resource changes validated successfully",
        )
        report.add_result(success_result)

        assert len(report.results) == 1
        assert report.overall_success is True

        # Add a failed result
        failure_result = ValidationResult(
            validation_type="pod_readiness",
            resource_type="Deployment",
            resource_name="test-app",
            namespace="default",
            success=False,
            message="Pods not ready",
        )
        report.add_result(failure_result)

        assert len(report.results) == 2
        assert report.overall_success is False  # Should be False now

        # Complete the report
        report.complete()

        assert report.completed_at is not None
        assert report.summary["total_validations"] == 2
        assert report.summary["successful_validations"] == 1
        assert report.summary["failed_validations"] == 1
        assert report.summary["success_rate"] == 50.0

    @pytest.mark.asyncio
    async def test_mock_validation_transaction(
        self,
        validator: PostExecutionValidator,
        sample_transaction: ExecutionTransaction,
        sample_resource_changes: List[ResourceChange],
    ) -> None:
        """Test validation of a transaction with mock commands."""
        report = await validator.validate_transaction(
            sample_transaction, sample_resource_changes
        )

        # Mock validation should succeed
        assert report.overall_success is True
        assert len(report.results) > 0

        # Should have multiple validation types
        validation_types = set(r.validation_type for r in report.results)
        expected_types = {
            "resource_changes",
            "resource_health",
            "pod_readiness",
            "pod_stability",
        }
        assert validation_types == expected_types

        # All mock validations should succeed
        for result in report.results:
            assert result.success is True
            assert "Mock validation" in result.message
            assert result.details.get("mock") is True

    @pytest.mark.asyncio
    async def test_validation_with_no_successful_commands(
        self,
        validator: PostExecutionValidator,
        sample_resource_changes: List[ResourceChange],
    ) -> None:
        """Test validation when no commands succeeded."""
        # Create transaction with failed commands
        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="failing-app",
            namespace="default",
            kubectl_args=["patch", "deployment", "failing-app"],
        )

        failed_result = ExecutionResult(
            command_id=command.command_id,
            status=ExecutionStatus.FAILED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_seconds=1.0,
            exit_code=1,
            stderr="deployment not found",
            error_message="Deployment not found",
        )

        transaction = ExecutionTransaction(
            confirmation_token_id="test-token-456",
            commands=[command],
            execution_mode=ExecutionMode.SINGLE,
            dry_run=False,
            command_results=[failed_result],
            overall_status=ExecutionStatus.FAILED,
            commands_completed=0,
            commands_failed=1,
        )

        report = await validator.validate_transaction(
            transaction, sample_resource_changes
        )

        # Should complete successfully but with no validation results
        assert report.overall_success is True  # No validations to fail
        assert len(report.results) == 0
        assert report.summary["total_validations"] == 0

    @pytest.mark.asyncio
    async def test_validation_result_serialization(self) -> None:
        """Test ValidationResult serialization to dictionary."""
        result = ValidationResult(
            validation_type="resource_changes",
            resource_type="Deployment",
            resource_name="test-app",
            namespace="default",
            success=True,
            message="Validation successful",
            details={"verified_resources": {"cpu": "200m", "memory": "256Mi"}},
        )

        result_dict = result.to_dict()

        assert result_dict["validation_type"] == "resource_changes"
        assert result_dict["resource_type"] == "Deployment"
        assert result_dict["resource_name"] == "test-app"
        assert result_dict["namespace"] == "default"
        assert result_dict["success"] is True
        assert result_dict["message"] == "Validation successful"
        assert result_dict["details"]["verified_resources"]["cpu"] == "200m"
        assert "timestamp" in result_dict

    @pytest.mark.asyncio
    async def test_validation_report_serialization(
        self,
        validator: PostExecutionValidator,
        sample_transaction: ExecutionTransaction,
        sample_resource_changes: List[ResourceChange],
    ) -> None:
        """Test ValidationReport serialization to dictionary."""
        report = await validator.validate_transaction(
            sample_transaction, sample_resource_changes
        )

        report_dict = report.to_dict()

        assert report_dict["transaction_id"] == sample_transaction.transaction_id
        assert "started_at" in report_dict
        assert "completed_at" in report_dict
        assert "overall_success" in report_dict
        assert "summary" in report_dict
        assert "results" in report_dict

        # Check summary structure
        summary = report_dict["summary"]
        assert "total_validations" in summary
        assert "successful_validations" in summary
        assert "failed_validations" in summary
        assert "success_rate" in summary
        assert "validation_types" in summary
        assert "duration_seconds" in summary

        # Check results structure
        results = report_dict["results"]
        assert len(results) > 0
        for result in results:
            assert "validation_type" in result
            assert "success" in result
            assert "message" in result

    @pytest.mark.asyncio
    async def test_change_mapping_creation(
        self, validator: PostExecutionValidator
    ) -> None:
        """Test creation of command-to-change mapping."""
        commands = [
            KubectlCommand(
                operation="patch",
                resource_type="Deployment",
                resource_name="app1",
                namespace="default",
                kubectl_args=["patch", "deployment", "app1"],
            ),
            KubectlCommand(
                operation="patch",
                resource_type="Deployment",
                resource_name="app2",
                namespace="default",
                kubectl_args=["patch", "deployment", "app2"],
            ),
        ]

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="app1",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
                cpu_change_percent=None,
                memory_change_percent=None,
                estimated_cost_impact=None,
            ),
            ResourceChange(
                object_kind="Deployment",
                object_name="app2",
                namespace="default",
                change_type=ChangeType.RESOURCE_DECREASE,
                current_values={"memory": "512Mi"},
                proposed_values={"memory": "256Mi"},
                cpu_change_percent=None,
                memory_change_percent=None,
                estimated_cost_impact=None,
            ),
        ]

        change_map = validator._create_change_mapping(commands, changes)

        assert len(change_map) == 2
        assert commands[0].command_id in change_map
        assert change_map[commands[0].command_id].object_name == "app1"
        assert commands[1].command_id in change_map
        assert change_map[commands[1].command_id].object_name == "app2"

    @pytest.mark.asyncio
    async def test_resource_request_verification_logic(
        self, validator: PostExecutionValidator
    ) -> None:
        """Test resource request verification logic."""
        # Mock manifest data
        manifest = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "app",
                                "resources": {
                                    "requests": {
                                        "cpu": "200m",
                                        "memory": "256Mi",
                                    }
                                },
                            }
                        ]
                    }
                }
            }
        }

        # Resource change that matches the manifest
        matching_change = ResourceChange(
            object_kind="Deployment",
            object_name="test-app",
            namespace="default",
            change_type=ChangeType.RESOURCE_INCREASE,
            current_values={"cpu": "100m", "memory": "128Mi"},
            proposed_values={"cpu": "200m", "memory": "256Mi"},
            cpu_change_percent=None,
            memory_change_percent=None,
            estimated_cost_impact=None,
        )

        success, message, details = validator._verify_resource_requests(
            manifest, matching_change
        )

        assert success is True
        assert "match expected values" in message
        assert "verified_resources" in details

        # Resource change that doesn't match the manifest
        non_matching_change = ResourceChange(
            object_kind="Deployment",
            object_name="test-app",
            namespace="default",
            change_type=ChangeType.RESOURCE_INCREASE,
            current_values={"cpu": "100m", "memory": "128Mi"},
            proposed_values={"cpu": "300m", "memory": "512Mi"},  # Different values
            cpu_change_percent=None,
            memory_change_percent=None,
            estimated_cost_impact=None,
        )

        success, message, details = validator._verify_resource_requests(
            manifest, non_matching_change
        )

        assert success is False
        assert "don't match expected values" in message
        assert "mismatches" in details
        assert len(details["mismatches"]) == 2  # Both CPU and memory mismatch

    @pytest.mark.asyncio
    async def test_deployment_health_check_logic(
        self, validator: PostExecutionValidator
    ) -> None:
        """Test deployment health check logic."""
        # Healthy deployment manifest
        healthy_manifest = {
            "status": {
                "replicas": 3,
                "readyReplicas": 3,
                "availableReplicas": 3,
                "conditions": [
                    {"type": "Available", "status": "True"},
                    {"type": "Progressing", "status": "True"},
                ],
            }
        }

        success, message, details = validator._check_resource_health(
            healthy_manifest, "deployment"
        )

        assert success is True
        assert "3/3 replicas ready" in message
        assert details["replicas"] == 3
        assert details["ready_replicas"] == 3
        assert details["available_replicas"] == 3

        # Unhealthy deployment manifest
        unhealthy_manifest = {
            "status": {
                "replicas": 3,
                "readyReplicas": 1,
                "availableReplicas": 1,
                "conditions": [
                    {"type": "Available", "status": "False"},
                    {"type": "Progressing", "status": "True"},
                ],
            }
        }

        success, message, details = validator._check_resource_health(
            unhealthy_manifest, "deployment"
        )

        assert success is False
        assert "1/3 replicas ready" in message
        assert details["replicas"] == 3
        assert details["ready_replicas"] == 1
        assert details["available_replicas"] == 1

    @pytest.mark.asyncio
    async def test_pod_readiness_check_logic(
        self, validator: PostExecutionValidator
    ) -> None:
        """Test pod readiness check logic."""
        # Ready pod
        ready_pod = {
            "status": {
                "phase": "Running",
                "conditions": [
                    {"type": "Ready", "status": "True"},
                    {"type": "ContainersReady", "status": "True"},
                ],
            }
        }

        is_ready, status = validator._check_pod_readiness(ready_pod)
        assert is_ready is True
        assert status == "Ready"

        # Not ready pod
        not_ready_pod = {
            "status": {
                "phase": "Running",
                "conditions": [
                    {
                        "type": "Ready",
                        "status": "False",
                        "reason": "ContainersNotReady",
                    },
                    {"type": "ContainersReady", "status": "False"},
                ],
            }
        }

        is_ready, status = validator._check_pod_readiness(not_ready_pod)
        assert is_ready is False
        assert "ContainersNotReady" in status

        # Pending pod
        pending_pod = {
            "status": {
                "phase": "Pending",
                "conditions": [],
            }
        }

        is_ready, status = validator._check_pod_readiness(pending_pod)
        assert is_ready is False
        assert "Pending" in status

    @pytest.mark.asyncio
    async def test_pod_stability_check_logic(
        self, validator: PostExecutionValidator
    ) -> None:
        """Test pod stability check logic."""
        # Stable pod
        stable_pod = {
            "status": {
                "containerStatuses": [
                    {
                        "name": "app",
                        "restartCount": 0,
                        "state": {"running": {"startedAt": "2024-01-01T00:00:00Z"}},
                    }
                ]
            }
        }

        is_stable, status = validator._check_pod_stability(stable_pod)
        assert is_stable is True
        assert status == "Stable"

        # High restart count pod
        high_restart_pod = {
            "status": {
                "containerStatuses": [
                    {
                        "name": "app",
                        "restartCount": 10,
                        "state": {"running": {"startedAt": "2024-01-01T00:00:00Z"}},
                    }
                ]
            }
        }

        is_stable, status = validator._check_pod_stability(high_restart_pod)
        assert is_stable is False
        assert "High restart count: 10" in status

        # Crash loop pod
        crash_loop_pod = {
            "status": {
                "containerStatuses": [
                    {
                        "name": "app",
                        "restartCount": 3,
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff",
                                "message": "Back-off restarting failed container",
                            }
                        },
                    }
                ]
            }
        }

        is_stable, status = validator._check_pod_stability(crash_loop_pod)
        assert is_stable is False
        assert "CrashLoopBackOff" in status


class TestKubectlExecutorValidation:
    """Test kubectl executor integration with post-execution validation."""

    @pytest.fixture
    async def executor(self) -> KubectlExecutor:
        """Create a kubectl executor with validation enabled."""
        confirmation_manager = ConfirmationManager(confirmation_timeout_minutes=5)
        executor = KubectlExecutor(
            kubeconfig_path="~/.kube/config",
            kubernetes_context="test-context",
            confirmation_manager=confirmation_manager,
            mock_commands=True,
            enable_post_validation=True,
        )
        return executor

    @pytest.fixture
    def sample_resource_changes(self) -> List[ResourceChange]:
        """Create sample resource changes."""
        return [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
                estimated_cost_impact=10.0,
            )
        ]

    @pytest.mark.asyncio
    async def test_executor_validation_integration(
        self,
        executor: KubectlExecutor,
        sample_resource_changes: List[ResourceChange],
    ) -> None:
        """Test kubectl executor integration with post-execution validation."""
        # Create and execute transaction
        transaction = await executor.create_transaction(
            changes=sample_resource_changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=True,
        )

        executed_transaction = await executor.execute_transaction(transaction)

        # Perform validation
        validation_report = await executor.validate_execution(
            executed_transaction, sample_resource_changes
        )

        assert validation_report is not None
        assert validation_report["overall_success"] is True
        assert validation_report["summary"]["total_validations"] > 0
        assert len(validation_report["results"]) > 0

        # Check that all validation types are covered
        validation_types = set(
            result["validation_type"] for result in validation_report["results"]
        )
        expected_types = {
            "resource_changes",
            "resource_health",
            "pod_readiness",
            "pod_stability",
        }
        assert validation_types == expected_types

    @pytest.mark.asyncio
    async def test_executor_validation_disabled(self) -> None:
        """Test kubectl executor with validation disabled."""
        confirmation_manager = ConfirmationManager(confirmation_timeout_minutes=5)
        executor = KubectlExecutor(
            kubeconfig_path="~/.kube/config",
            kubernetes_context="test-context",
            confirmation_manager=confirmation_manager,
            mock_commands=True,
            enable_post_validation=False,  # Disabled
        )

        # Validator should not be initialized
        assert executor.post_validator is None
        assert executor.enable_post_validation is False

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
                cpu_change_percent=None,
                memory_change_percent=None,
                estimated_cost_impact=None,
            )
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=True,
        )

        executed_transaction = await executor.execute_transaction(transaction)

        # Validation should return None when disabled
        validation_report = await executor.validate_execution(
            executed_transaction, changes
        )

        assert validation_report is None

    @pytest.mark.asyncio
    async def test_validation_with_failed_transaction(
        self,
        executor: KubectlExecutor,
        sample_resource_changes: List[ResourceChange],
    ) -> None:
        """Test validation with a transaction that has failed commands."""
        # Create transaction
        transaction = await executor.create_transaction(
            changes=sample_resource_changes,
            confirmation_token_id="test-token-456",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=True,
        )

        # Create a failing command
        failing_command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="failing-app",  # This will trigger mock failure
            namespace="default",
            kubectl_args=["patch", "deployment", "failing-app"],
        )

        # Replace with failing command
        transaction.commands = [failing_command]

        executed_transaction = await executor.execute_transaction(transaction)

        # Validation should still work but have no results
        validation_report = await executor.validate_execution(
            executed_transaction, sample_resource_changes
        )

        assert validation_report is not None
        assert validation_report["overall_success"] is True  # No validations to fail
        assert validation_report["summary"]["total_validations"] == 0
        assert len(validation_report["results"]) == 0


class TestPostExecutionValidatorEdgeCases:
    """Test edge cases and error conditions for post-execution validation."""

    @pytest.fixture
    def non_mock_validator(self) -> PostExecutionValidator:
        """Create a post-execution validator without mock mode."""
        return PostExecutionValidator(
            kubeconfig_path="~/.kube/config",
            kubernetes_context="test-context",
            mock_commands=False,  # Non-mock mode to test real execution paths
            validation_timeout=60,
            readiness_wait_time=1,  # Short wait for testing
        )

    @pytest.mark.asyncio
    async def test_validation_error_handling(
        self, non_mock_validator: PostExecutionValidator
    ) -> None:
        """Test validation error handling for unexpected exceptions."""
        # Create a transaction that will cause validation errors
        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="test-app",
            namespace="default",
            kubectl_args=["patch", "deployment", "test-app"],
        )

        result = ExecutionResult(
            command_id=command.command_id,
            status=ExecutionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_seconds=1.0,
            exit_code=0,
            stdout="deployment.apps/test-app patched",
        )

        transaction = ExecutionTransaction(
            confirmation_token_id="test-token-123",
            commands=[command],
            execution_mode=ExecutionMode.SINGLE,
            dry_run=False,
            command_results=[result],
            overall_status=ExecutionStatus.COMPLETED,
        )

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
                estimated_cost_impact=10.0,
            )
        ]

        # Mock a scenario where validation itself throws an exception
        with patch.object(
            non_mock_validator,
            "_get_resource_manifest",
            side_effect=Exception("Network error"),
        ):
            report = await non_mock_validator.validate_transaction(transaction, changes)

            # Should complete but with error results
            assert report.overall_success is False
            assert len(report.results) > 0

            # Should have validation error results
            error_results = [r for r in report.results if not r.success]
            assert len(error_results) > 0

    @pytest.mark.asyncio
    async def test_resource_not_found_after_changes(
        self, non_mock_validator: PostExecutionValidator
    ) -> None:
        """Test validation when resource is not found after applying changes."""
        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="missing-app",
            namespace="default",
            kubectl_args=["patch", "deployment", "missing-app"],
        )

        result = ExecutionResult(
            command_id=command.command_id,
            status=ExecutionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_seconds=1.0,
            exit_code=0,
            stdout="deployment.apps/missing-app patched",
        )

        transaction = ExecutionTransaction(
            confirmation_token_id="test-token-123",
            commands=[command],
            execution_mode=ExecutionMode.SINGLE,
            dry_run=False,
            command_results=[result],
            overall_status=ExecutionStatus.COMPLETED,
        )

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="missing-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
                cpu_change_percent=100.0,
                memory_change_percent=0.0,
                estimated_cost_impact=5.0,
            )
        ]

        # Mock resource not found
        with patch.object(
            non_mock_validator, "_get_resource_manifest", return_value=None
        ):
            report = await non_mock_validator.validate_transaction(transaction, changes)

            # Should complete but with failures
            assert report.overall_success is False
            assert len(report.results) > 0

            # Should have "resource not found" failures
            not_found_results = [
                r
                for r in report.results
                if not r.success and "not found" in r.message.lower()
            ]
            assert len(not_found_results) > 0

    @pytest.mark.asyncio
    async def test_validation_timeout_scenarios(
        self, non_mock_validator: PostExecutionValidator
    ) -> None:
        """Test validation scenarios with timeouts."""
        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="timeout-app",
            namespace="default",
            kubectl_args=["patch", "deployment", "timeout-app"],
        )

        result = ExecutionResult(
            command_id=command.command_id,
            status=ExecutionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_seconds=1.0,
            exit_code=0,
            stdout="deployment.apps/timeout-app patched",
        )

        transaction = ExecutionTransaction(
            confirmation_token_id="test-token-123",
            commands=[command],
            execution_mode=ExecutionMode.SINGLE,
            dry_run=False,
            command_results=[result],
            overall_status=ExecutionStatus.COMPLETED,
        )

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="timeout-app",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
                cpu_change_percent=100.0,
                memory_change_percent=0.0,
                estimated_cost_impact=5.0,
            )
        ]

        # Mock timeout in kubectl command
        async def mock_timeout_exec(*args, **kwargs):
            raise asyncio.TimeoutError("Command timed out")

        with patch("asyncio.create_subprocess_exec", side_effect=mock_timeout_exec):
            report = await non_mock_validator.validate_transaction(transaction, changes)

            # Should complete but with timeout-related failures
            assert report.overall_success is False
            assert len(report.results) > 0

    @pytest.mark.asyncio
    async def test_pod_validation_for_non_pod_resources(
        self, non_mock_validator: PostExecutionValidator
    ) -> None:
        """Test that pod validation is skipped for non-pod controlling resources."""
        command = KubectlCommand(
            operation="patch",
            resource_type="ConfigMap",  # ConfigMap doesn't control pods
            resource_name="test-config",
            namespace="default",
            kubectl_args=["patch", "configmap", "test-config"],
        )

        result = ExecutionResult(
            command_id=command.command_id,
            status=ExecutionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_seconds=1.0,
            exit_code=0,
            stdout="configmap/test-config patched",
        )

        transaction = ExecutionTransaction(
            confirmation_token_id="test-token-123",
            commands=[command],
            execution_mode=ExecutionMode.SINGLE,
            dry_run=False,
            command_results=[result],
            overall_status=ExecutionStatus.COMPLETED,
        )

        changes = [
            ResourceChange(
                object_kind="ConfigMap",
                object_name="test-config",
                namespace="default",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"data": "old"},
                proposed_values={"data": "new"},
                cpu_change_percent=0.0,
                memory_change_percent=0.0,
                estimated_cost_impact=0.0,
            )
        ]

        # Mock successful resource retrieval
        mock_manifest = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "test-config", "namespace": "default"},
            "data": {"config": "new"},
        }

        with patch.object(
            non_mock_validator, "_get_resource_manifest", return_value=mock_manifest
        ):
            report = await non_mock_validator.validate_transaction(transaction, changes)

            # Should complete but only with resource change validation (no pod validations)
            validation_types = set(r.validation_type for r in report.results)
            assert "resource_changes" in validation_types
            assert (
                "pod_readiness" not in validation_types
            )  # Should be skipped for ConfigMap
            assert (
                "pod_stability" not in validation_types
            )  # Should be skipped for ConfigMap

    @pytest.mark.asyncio
    async def test_verify_resource_requests_without_containers(self) -> None:
        """Test resource request verification with manifest without containers."""
        validator = PostExecutionValidator(mock_commands=True)

        # Manifest without containers
        manifest = {"spec": {"template": {"spec": {}}}}  # No containers key

        change = ResourceChange(
            object_kind="Deployment",
            object_name="test-app",
            namespace="default",
            change_type=ChangeType.RESOURCE_INCREASE,
            current_values={"cpu": "100m"},
            proposed_values={"cpu": "200m"},
            cpu_change_percent=100.0,
            memory_change_percent=0.0,
            estimated_cost_impact=5.0,
        )

        success, message, details = validator._verify_resource_requests(
            manifest, change
        )

        assert success is False
        assert "No containers found" in message

    @pytest.mark.asyncio
    async def test_verify_resource_requests_with_none_change(self) -> None:
        """Test resource request verification with None original change."""
        validator = PostExecutionValidator(mock_commands=True)

        manifest = {"spec": {"template": {"spec": {"containers": []}}}}

        success, message, details = validator._verify_resource_requests(manifest, None)

        assert success is True
        assert "No original change data" in message

    @pytest.mark.asyncio
    async def test_check_resource_health_generic_resource(self) -> None:
        """Test health check for generic (non-deployment) resources."""
        validator = PostExecutionValidator(mock_commands=True)

        # Generic resource with conditions
        manifest = {
            "status": {
                "conditions": [
                    {"type": "Available", "status": "True"},
                    {"type": "Ready", "status": "True"},
                    {"type": "Failed", "status": "False"},
                ]
            }
        }

        success, message, details = validator._check_resource_health(
            manifest, "Service"
        )

        assert success is True
        assert "2 healthy conditions" in message
        assert details["healthy_conditions"] == 2

    @pytest.mark.asyncio
    async def test_check_pod_readiness_without_conditions(self) -> None:
        """Test pod readiness check for pod without Ready condition."""
        validator = PostExecutionValidator(mock_commands=True)

        pod = {
            "status": {
                "phase": "Running",
                "conditions": [
                    {"type": "ContainersReady", "status": "True"},
                    # No Ready condition
                ],
            }
        }

        is_ready, status = validator._check_pod_readiness(pod)

        assert is_ready is False
        assert "No Ready condition found" in status

    @pytest.mark.asyncio
    async def test_check_pod_stability_with_waiting_containers(self) -> None:
        """Test pod stability check with containers in waiting state."""
        validator = PostExecutionValidator(mock_commands=True)

        pod = {
            "status": {
                "containerStatuses": [
                    {
                        "name": "app",
                        "restartCount": 2,
                        "state": {
                            "waiting": {
                                "reason": "ImagePullBackOff",
                                "message": "Failed to pull image",
                            }
                        },
                    }
                ]
            }
        }

        is_stable, status = validator._check_pod_stability(pod)

        assert is_stable is False
        assert "ImagePullBackOff" in status

    @pytest.mark.asyncio
    async def test_find_command_by_id_not_found(self) -> None:
        """Test finding command by ID when not found."""
        validator = PostExecutionValidator(mock_commands=True)

        commands = [
            KubectlCommand(
                operation="patch",
                resource_type="Deployment",
                resource_name="app1",
                namespace="default",
                kubectl_args=["patch", "deployment", "app1"],
            )
        ]

        result = validator._find_command_by_id(commands, "nonexistent-id")

        assert result is None
