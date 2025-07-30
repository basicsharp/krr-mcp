"""Tests for staged rollout functionality in kubectl executor."""

import asyncio
from typing import Dict, List
from unittest.mock import AsyncMock

import pytest

from src.executor.kubectl_executor import KubectlExecutor
from src.executor.models import (
    ExecutionMode,
    ExecutionStatus,
    KubectlCommand,
)
from src.safety.confirmation_manager import ConfirmationManager
from src.safety.models import ChangeType, ResourceChange


class TestStagedRollout:
    """Test staged rollout execution functionality."""

    @pytest.fixture
    async def executor(self) -> KubectlExecutor:
        """Create a kubectl executor with mock commands."""
        confirmation_manager = ConfirmationManager(confirmation_timeout_minutes=5)
        executor = KubectlExecutor(
            kubeconfig_path="~/.kube/config",
            kubernetes_context="test-context",
            confirmation_manager=confirmation_manager,
            mock_commands=True,
        )
        return executor

    @pytest.fixture
    def sample_commands(self) -> List[KubectlCommand]:
        """Create sample commands across multiple namespaces."""
        return [
            # Development namespace (should be deployed first - lowest criticality)
            KubectlCommand(
                operation="apply",
                resource_type="deployment",
                resource_name="app-dev",
                namespace="development",
                kubectl_args=["apply", "-f", "/dev/null"],
            ),
            KubectlCommand(
                operation="apply",
                resource_type="configmap",
                resource_name="config-dev",
                namespace="development",
                kubectl_args=["apply", "-f", "/dev/null"],
            ),
            # Staging namespace (should be deployed second - medium criticality)
            KubectlCommand(
                operation="apply",
                resource_type="deployment",
                resource_name="app-staging",
                namespace="staging",
                kubectl_args=["apply", "-f", "/dev/null"],
            ),
            # Production namespace (should be deployed last - highest criticality)
            KubectlCommand(
                operation="apply",
                resource_type="deployment",
                resource_name="app-prod",
                namespace="production",
                kubectl_args=["apply", "-f", "/dev/null"],
            ),
            KubectlCommand(
                operation="apply",
                resource_type="service",
                resource_name="svc-prod",
                namespace="production",
                kubectl_args=["apply", "-f", "/dev/null"],
            ),
        ]

    @pytest.mark.asyncio
    async def test_staged_rollout_execution(
        self, executor: KubectlExecutor, sample_commands: List[KubectlCommand]
    ) -> None:
        """Test basic staged rollout execution."""
        # Create transaction with staged mode
        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="development",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=None,
                memory_change_percent=None,
                estimated_cost_impact=None,
            )
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.STAGED,
            dry_run=True,
        )

        # Override commands with our sample commands for testing
        transaction.commands = sample_commands

        # Track progress calls
        progress_calls = []

        def progress_callback(tx, progress):
            progress_calls.append(progress.copy())

        # Execute transaction
        executed_transaction = await executor.execute_transaction(
            transaction, progress_callback=progress_callback
        )

        # Verify transaction completed
        assert executed_transaction.overall_status == ExecutionStatus.COMPLETED
        assert executed_transaction.commands_completed == len(sample_commands)
        assert executed_transaction.commands_failed == 0

        # Verify progress callbacks were called with stage information
        assert len(progress_calls) > 0

        # Check that stage information was included in progress
        stage_info_calls = [call for call in progress_calls if "current_stage" in call]
        assert len(stage_info_calls) > 0

        # Verify stages progressed correctly
        for call in stage_info_calls:
            assert "current_stage" in call
            assert "total_stages" in call
            assert "stage_info" in call
            assert call["current_stage"] <= call["total_stages"]

    @pytest.mark.asyncio
    async def test_namespace_grouping(
        self, executor: KubectlExecutor, sample_commands: List[KubectlCommand]
    ) -> None:
        """Test command grouping by namespace."""
        groups = executor._group_commands_by_namespace(sample_commands)

        # Should have 3 groups: development, staging, production
        assert len(groups) == 3

        # Verify each namespace has correct commands
        namespace_map = dict(groups)

        assert "development" in namespace_map
        assert len(namespace_map["development"]) == 2  # app-dev, config-dev

        assert "staging" in namespace_map
        assert len(namespace_map["staging"]) == 1  # app-staging

        assert "production" in namespace_map
        assert len(namespace_map["production"]) == 2  # app-prod, svc-prod

    @pytest.mark.asyncio
    async def test_criticality_sorting(
        self, executor: KubectlExecutor, sample_commands: List[KubectlCommand]
    ) -> None:
        """Test namespace sorting by criticality."""
        groups = executor._group_commands_by_namespace(sample_commands)
        sorted_groups = executor._sort_namespace_groups_by_criticality(groups)

        # Should be sorted by criticality (least to most critical)
        namespace_order = [namespace for namespace, _ in sorted_groups]

        # Check that we have all expected namespaces
        assert "development" in namespace_order
        assert "staging" in namespace_order
        assert "production" in namespace_order

        # Production should come last (most critical due to "prod" keyword match)
        assert namespace_order[-1] == "production"

        # Development should have lower criticality than production
        dev_index = namespace_order.index("development")
        prod_index = namespace_order.index("production")
        assert dev_index < prod_index, "Development should come before production"

    @pytest.mark.asyncio
    async def test_canary_delay_calculation(self, executor: KubectlExecutor) -> None:
        """Test canary delay calculation."""
        # Single stage should have no delay
        assert executor._calculate_canary_delay(1, 1) == 0.0

        # Since executor is created with mock_commands=True, we get mock delays
        # First stage of multi-stage should have longest delay (mock version)
        assert executor._calculate_canary_delay(1, 3) == 0.1

        # Middle stage should have moderate delay (mock version)
        assert executor._calculate_canary_delay(2, 4) == 0.05

        # Later stages should have shorter delay (mock version)
        assert executor._calculate_canary_delay(3, 4) == 0.01

    @pytest.mark.asyncio
    async def test_staged_rollout_with_failure(self, executor: KubectlExecutor) -> None:
        """Test staged rollout behavior when a command fails."""
        # Create commands that will fail (using mock failure simulation)
        failing_command = KubectlCommand(
            operation="apply",
            resource_type="deployment",
            resource_name="failing-app",
            namespace="development",
            kubectl_args=[
                "apply",
                "-f",
                "/nonexistent/file",
            ],  # This will fail in mock mode
        )

        success_command = KubectlCommand(
            operation="apply",
            resource_type="deployment",
            resource_name="success-app",
            namespace="production",
            kubectl_args=["apply", "-f", "/dev/null"],
        )

        commands = [failing_command, success_command]

        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="failing-app",
                namespace="development",
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
            confirmation_token_id="test-token-456",
            execution_mode=ExecutionMode.STAGED,
            dry_run=True,
        )

        # Override with our test commands
        transaction.commands = commands

        # Execute transaction
        executed_transaction = await executor.execute_transaction(transaction)

        # Verify that failure was handled appropriately
        assert executed_transaction.overall_status == ExecutionStatus.FAILED
        assert executed_transaction.commands_failed >= 1

        # Check that we have both successful and failed results
        failed_commands = executed_transaction.get_failed_commands()
        assert len(failed_commands) >= 1

    @pytest.mark.asyncio
    async def test_staged_rollout_progress_tracking(
        self, executor: KubectlExecutor, sample_commands: List[KubectlCommand]
    ) -> None:
        """Test detailed progress tracking during staged rollout."""
        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="development",
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
            confirmation_token_id="test-token-789",
            execution_mode=ExecutionMode.STAGED,
            dry_run=True,
        )

        transaction.commands = sample_commands

        # Detailed progress tracking
        progress_history = []

        def detailed_progress_callback(tx, progress):
            progress_entry = {
                "timestamp": asyncio.get_event_loop().time(),
                "progress_percent": progress["progress_percent"],
                "completed": progress["completed"],
                "failed": progress["failed"],
                "current_stage": progress.get("current_stage"),
                "total_stages": progress.get("total_stages"),
                "stage_info": progress.get("stage_info"),
            }
            progress_history.append(progress_entry)

        # Execute with detailed tracking
        executed_transaction = await executor.execute_transaction(
            transaction, progress_callback=detailed_progress_callback
        )

        # Verify detailed progress was tracked
        assert len(progress_history) >= len(sample_commands)

        # Verify progress percentages increased
        percentages = [entry["progress_percent"] for entry in progress_history]
        assert percentages == sorted(percentages)  # Should be non-decreasing

        # Verify final progress is 100%
        assert progress_history[-1]["progress_percent"] == 100.0

        # Verify stage information was tracked
        stage_entries = [
            entry for entry in progress_history if entry["current_stage"] is not None
        ]
        assert len(stage_entries) > 0

        # Verify stage progression
        stages = [entry["current_stage"] for entry in stage_entries]
        assert min(stages) >= 1
        assert max(stages) <= max(
            entry["total_stages"] for entry in stage_entries if entry["total_stages"]
        )

    @pytest.mark.asyncio
    async def test_staged_mode_vs_other_modes(
        self, executor: KubectlExecutor, sample_commands: List[KubectlCommand]
    ) -> None:
        """Test that staged mode behaves differently from single and batch modes."""
        changes = [
            ResourceChange(
                object_kind="Deployment",
                object_name="test-app",
                namespace="development",
                change_type=ChangeType.RESOURCE_INCREASE,
                current_values={"cpu": "100m"},
                proposed_values={"cpu": "200m"},
                cpu_change_percent=None,
                memory_change_percent=None,
                estimated_cost_impact=None,
            )
        ]

        # Test staged mode
        staged_progress_calls = []
        staged_transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="staged-token",
            execution_mode=ExecutionMode.STAGED,
            dry_run=True,
        )
        staged_transaction.commands = sample_commands

        def staged_callback(tx, progress):
            staged_progress_calls.append(progress.copy())

        await executor.execute_transaction(staged_transaction, staged_callback)

        # Test single mode for comparison
        single_progress_calls = []
        single_transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="single-token",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=True,
        )
        single_transaction.commands = sample_commands

        def single_callback(tx, progress):
            single_progress_calls.append(progress.copy())

        await executor.execute_transaction(single_transaction, single_callback)

        # Verify staged mode has additional stage information
        staged_with_stages = len(
            [call for call in staged_progress_calls if "current_stage" in call]
        )
        single_with_stages = len(
            [call for call in single_progress_calls if "current_stage" in call]
        )

        assert staged_with_stages > single_with_stages
        assert staged_with_stages > 0
        assert single_with_stages == 0  # Single mode should not have stage info
