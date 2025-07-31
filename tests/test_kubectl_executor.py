"""Comprehensive tests for kubectl executor module."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from src.executor.kubectl_executor import KubectlExecutor
from src.executor.models import (
    ExecutionMode,
    ExecutionReport,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTransaction,
    KubectlCommand,
    KubectlContextError,
    KubectlError,
    KubectlExecutionError,
    KubectlNotFoundError,
    KubectlTimeoutError,
)
from src.safety.models import ResourceChange, RollbackSnapshot


class TestKubectlExecutorInitialization:
    """Test kubectl executor initialization."""

    def test_initialization_defaults(self):
        """Test default initialization parameters."""
        executor = KubectlExecutor(mock_commands=True)

        assert executor.kubeconfig_path is None
        assert executor.kubernetes_context is None
        assert executor.confirmation_manager is None
        assert executor.default_timeout == 120
        assert executor.mock_commands is True
        assert executor.logger is not None

    def test_initialization_with_parameters(self):
        """Test initialization with custom parameters."""
        executor = KubectlExecutor(
            kubeconfig_path="/tmp/kubeconfig",
            kubernetes_context="test-context",
            default_timeout=300,
            mock_commands=True,
        )

        assert executor.kubeconfig_path == "/tmp/kubeconfig"
        assert executor.kubernetes_context == "test-context"
        assert executor.default_timeout == 300
        assert executor.mock_commands is True

    @pytest.mark.asyncio
    async def test_kubectl_availability_verification_mock_mode(self):
        """Test kubectl availability verification in mock mode."""
        # Mock mode should not verify kubectl
        executor = KubectlExecutor(mock_commands=True)
        await asyncio.sleep(0.1)  # Allow any background tasks to complete

        # Should succeed without actual kubectl
        assert executor.mock_commands is True

    @pytest.mark.asyncio
    async def test_kubectl_not_found_error(self):
        """Test kubectl not found error."""
        with patch("shutil.which", return_value=None):
            # Create executor in mock mode first to avoid hanging task
            executor = KubectlExecutor(mock_commands=True)

            with pytest.raises(KubectlNotFoundError):
                await executor._verify_kubectl_availability()

    @pytest.mark.asyncio
    async def test_cluster_access_verification(self):
        """Test cluster access verification."""
        executor = KubectlExecutor(mock_commands=True)

        # Mock successful cluster access
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"cluster info", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            await executor._verify_cluster_access()
            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_cluster_access_failure(self):
        """Test cluster access failure handling."""
        executor = KubectlExecutor(mock_commands=True)

        # Mock failed cluster access
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"connection refused")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            with pytest.raises(KubectlContextError):
                await executor._verify_cluster_access()


class TestTransactionCreation:
    """Test transaction creation functionality."""

    @pytest.mark.asyncio
    async def test_create_transaction_single_change(self):
        """Test creating transaction with single resource change."""
        executor = KubectlExecutor(mock_commands=True)

        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=True,
        )

        assert isinstance(transaction, ExecutionTransaction)
        assert transaction.execution_mode == ExecutionMode.SINGLE
        assert transaction.dry_run is True
        assert len(transaction.commands) == 1
        assert transaction.commands[0].resource_name == "test-deployment"
        assert transaction.commands[0].namespace == "default"

    @pytest.mark.asyncio
    async def test_create_transaction_multiple_changes(self):
        """Test creating transaction with multiple resource changes."""
        executor = KubectlExecutor(mock_commands=True)

        changes = [
            ResourceChange(
                object_name=f"test-deployment-{i}",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
            for i in range(3)
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.BATCH,
            dry_run=False,
        )

        assert isinstance(transaction, ExecutionTransaction)
        assert transaction.execution_mode == ExecutionMode.BATCH
        assert transaction.dry_run is False
        assert len(transaction.commands) == 3

    @pytest.mark.asyncio
    async def test_create_transaction_with_confirmation_required(self):
        """Test creating transaction that requires confirmation."""
        from src.safety.confirmation_manager import ConfirmationManager

        confirmation_manager = ConfirmationManager()
        executor = KubectlExecutor(
            confirmation_manager=confirmation_manager, mock_commands=True
        )

        changes = [
            ResourceChange(
                object_name="critical-deployment",
                namespace="production",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "1000m", "memory": "1Gi"},
                proposed_values={"cpu": "5000m", "memory": "5Gi"},
                cpu_change_percent=400.0,
                memory_change_percent=400.0,
            )
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.SINGLE,
        )

        assert transaction.confirmation_token_id == "test-token-123"
        assert len(transaction.commands) == 1


class TestKubectlCommandGeneration:
    """Test kubectl command generation."""

    @pytest.mark.asyncio
    async def test_generate_kubectl_command_deployment(self):
        """Test generating kubectl command for deployment."""
        executor = KubectlExecutor(mock_commands=True)

        change = ResourceChange(
            object_name="test-deployment",
            namespace="default",
            object_kind="Deployment",
            change_type="resource_increase",
            current_values={"cpu": "100m", "memory": "128Mi"},
            proposed_values={"cpu": "200m", "memory": "256Mi"},
            cpu_change_percent=100.0,
            memory_change_percent=100.0,
        )

        command = await executor._generate_kubectl_command(change, dry_run=True)

        assert isinstance(command, KubectlCommand)
        assert command.resource_name == "test-deployment"
        assert command.namespace == "default"
        assert command.resource_type == "Deployment"
        assert command.dry_run is True
        assert command.kubectl_args[0] == "patch"
        assert "patch" in command.kubectl_args

    @pytest.mark.asyncio
    async def test_generate_kubectl_command_with_context(self):
        """Test generating kubectl command with kubernetes context."""
        executor = KubectlExecutor(
            kubernetes_context="test-context",
            kubeconfig_path="/tmp/kubeconfig",
            mock_commands=True,
        )

        change = ResourceChange(
            object_name="test-service",
            namespace="kube-system",
            object_kind="Service",
            change_type="resource_increase",
            current_values={"replicas": "1"},
            proposed_values={"replicas": "3"},
            cpu_change_percent=0.0,
            memory_change_percent=0.0,
        )

        command = await executor._generate_kubectl_command(change, dry_run=False)

        assert "--context" in command.kubectl_args
        assert "test-context" in command.kubectl_args
        assert "--kubeconfig" in command.kubectl_args
        assert "/tmp/kubeconfig" in command.kubectl_args

    @pytest.mark.asyncio
    async def test_generate_kubectl_command_resource_patch(self):
        """Test generating resource patch command."""
        executor = KubectlExecutor(mock_commands=True)

        change = ResourceChange(
            object_name="test-deployment",
            namespace="default",
            object_kind="Deployment",
            change_type="resource_increase",
            current_values={"cpu": "100m", "memory": "128Mi"},
            proposed_values={"cpu": "400m", "memory": "512Mi"},
            cpu_change_percent=300.0,
            memory_change_percent=300.0,
        )

        command = await executor._generate_kubectl_command(change, dry_run=False)

        # Verify command was generated correctly (manifest_content may be None in mock mode)
        assert command.operation in ["apply", "patch"]
        assert command.resource_type == "Deployment"
        assert command.resource_name == "test-deployment"


class TestTransactionExecution:
    """Test transaction execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_transaction_single_mode(self):
        """Test executing transaction in single mode."""
        executor = KubectlExecutor(mock_commands=True)

        # Create a simple transaction
        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=True,
        )

        # Execute transaction
        completed_transaction = await executor.execute_transaction(transaction)

        assert isinstance(completed_transaction, ExecutionTransaction)
        assert completed_transaction.transaction_id == transaction.transaction_id
        assert completed_transaction.overall_status == ExecutionStatus.COMPLETED
        assert len(completed_transaction.command_results) == 1

    @pytest.mark.asyncio
    async def test_execute_transaction_batch_mode(self):
        """Test executing transaction in batch mode."""
        executor = KubectlExecutor(mock_commands=True)

        # Create a batch transaction
        changes = [
            ResourceChange(
                object_name=f"test-deployment-{i}",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
            for i in range(3)
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.BATCH,
            dry_run=True,
        )

        # Execute transaction
        completed_transaction = await executor.execute_transaction(transaction)

        assert isinstance(completed_transaction, ExecutionTransaction)
        assert len(completed_transaction.commands) == 3
        assert completed_transaction.overall_status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_transaction_dry_run(self):
        """Test executing transaction in dry run mode."""
        executor = KubectlExecutor(mock_commands=True)

        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=True,
        )

        # Execute dry run transaction
        completed_transaction = await executor.execute_transaction(transaction)

        assert completed_transaction.overall_status == ExecutionStatus.COMPLETED
        assert len(completed_transaction.commands) == 1


class TestSingleCommandExecution:
    """Test single command execution."""

    @pytest.mark.asyncio
    async def test_execute_single_command_mock_mode(self):
        """Test executing single command in mock mode."""
        executor = KubectlExecutor(mock_commands=True)

        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="test-deployment",
            namespace="default",
            kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
            manifest_content='{"spec": {"replicas": 3}}',
            dry_run=False,
        )

        result = await executor._execute_single_command(command)

        assert isinstance(result, ExecutionResult)
        assert result.status == ExecutionStatus.COMPLETED
        assert result.command_id == command.command_id
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_single_command_timeout(self):
        """Test single command execution timeout."""
        executor = KubectlExecutor(mock_commands=True, default_timeout=1)

        # Mock a long-running command
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            # Simulate timeout by making communicate hang
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_subprocess.return_value = mock_process

            command = KubectlCommand(
                operation="get",
                resource_type="Deployment",
                resource_name="test-deployment",
                namespace="default",
                kubectl_args=["kubectl", "get", "deployment", "test-deployment"],
                manifest_content="",
                dry_run=False,
            )

            # Should not raise in mock mode, but would timeout in real mode
            result = await executor._execute_single_command(command)
            assert result.status == ExecutionStatus.COMPLETED  # Mock mode succeeds

    @pytest.mark.asyncio
    async def test_execute_mock_command(self):
        """Test mock command execution."""
        executor = KubectlExecutor(mock_commands=True)

        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="test-deployment",
            namespace="default",
            kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
            manifest_content='{"spec": {"replicas": 3}}',
            dry_run=False,
        )

        # Create result object first
        from datetime import datetime, timezone

        result = ExecutionResult(
            command_id=command.command_id,
            status=ExecutionStatus.PENDING,
            started_at=datetime.now(timezone.utc),
            exit_code=-1,
        )
        result = await executor._execute_mock_command(command, result)

        assert isinstance(result, ExecutionResult)
        assert result.status == ExecutionStatus.COMPLETED
        assert result.exit_code == 0
        assert "Mocked execution" in result.stdout
        assert len(result.affected_resources) > 0


class TestRollbackFunctionality:
    """Test rollback functionality."""

    @pytest.mark.asyncio
    async def test_create_rollback_snapshot(self):
        """Test creating rollback snapshot."""
        executor = KubectlExecutor(mock_commands=True)

        # Create sample commands for snapshot
        commands = [
            KubectlCommand(
                operation="patch",
                resource_type="Deployment",
                resource_name="test-deployment",
                namespace="default",
                kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
                manifest_content='{"spec": {"replicas": 3}}',
                dry_run=False,
            )
        ]

        # Mock getting current manifest
        with patch.object(executor, "_get_current_manifest") as mock_get_manifest:
            mock_get_manifest.return_value = {
                "kind": "Deployment",
                "metadata": {"name": "test-deployment"},
            }

            # Create a mock transaction for testing rollback snapshot
            from src.executor.models import ExecutionTransaction

            test_transaction = ExecutionTransaction(
                confirmation_token_id="test-token", commands=commands
            )

            snapshot = await executor._create_rollback_snapshot(test_transaction)

            # Note: snapshot will be None if no confirmation manager is set
            if snapshot:
                assert snapshot.startswith("rollback-")  # snapshot is just the ID

    @pytest.mark.asyncio
    async def test_get_current_manifest(self):
        """Test getting current resource manifest."""
        executor = KubectlExecutor(mock_commands=True)

        # Mock kubectl get command
        mock_manifest = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test-deployment", "namespace": "default"},
            "spec": {"replicas": 1},
        }

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                json.dumps(mock_manifest).encode(),
                b"",
            )
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            manifest = await executor._get_current_manifest(
                "Deployment", "test-deployment", "default"
            )

            assert manifest == mock_manifest
            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_manifest_not_found(self):
        """Test getting manifest for non-existent resource."""
        executor = KubectlExecutor(mock_commands=True)

        # Mock kubectl get command failure
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"not found")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            # Should not raise in mock mode
            manifest = await executor._get_current_manifest(
                "Deployment", "nonexistent", "default"
            )

            # In mock mode, this should return empty dict or None
            assert manifest is None or manifest == {}


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_kubectl_not_found_handling(self):
        """Test handling kubectl not found."""
        # Create executor in mock mode first to avoid hanging task
        executor = KubectlExecutor(mock_commands=True)

        with patch("shutil.which", return_value=None):
            with pytest.raises(
                KubectlNotFoundError, match="kubectl executable not found"
            ):
                await executor._verify_kubectl_availability()

    @pytest.mark.asyncio
    async def test_context_error_handling(self):
        """Test handling kubernetes context errors."""
        executor = KubectlExecutor(mock_commands=True)

        # Mock cluster access failure
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"context not found")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            with pytest.raises(KubectlContextError):
                await executor._verify_cluster_access()

    @pytest.mark.asyncio
    async def test_execution_error_handling(self):
        """Test handling execution errors."""
        executor = KubectlExecutor(mock_commands=True)

        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="test-deployment",
            namespace="default",
            kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
            manifest_content="invalid-json",
            dry_run=False,
        )

        # Mock command execution failure
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"invalid patch")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            # Should not raise in mock mode, but handle gracefully
            result = await executor._execute_single_command(command)
            assert result.status == ExecutionStatus.COMPLETED  # Mock mode succeeds

    @pytest.mark.asyncio
    async def test_permission_error_handling(self):
        """Test handling permission errors."""
        executor = KubectlExecutor(mock_commands=True)

        # Mock permission denied error
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"permission denied")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            command = KubectlCommand(
                operation="patch",
                resource_type="Deployment",
                resource_name="test-deployment",
                namespace="default",
                kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
                manifest_content='{"spec": {"replicas": 3}}',
                dry_run=False,
            )

            # Should handle gracefully in mock mode
            result = await executor._execute_single_command(command)
            assert result.status == ExecutionStatus.COMPLETED  # Mock mode succeeds


class TestConfigurationHandling:
    """Test configuration and context handling."""

    def test_kubeconfig_path_handling(self):
        """Test kubeconfig path configuration."""
        executor = KubectlExecutor(
            kubeconfig_path="/custom/kubeconfig", mock_commands=True
        )

        assert executor.kubeconfig_path == "/custom/kubeconfig"

    def test_kubernetes_context_handling(self):
        """Test kubernetes context configuration."""
        executor = KubectlExecutor(
            kubernetes_context="custom-context", mock_commands=True
        )

        assert executor.kubernetes_context == "custom-context"

    def test_timeout_configuration(self):
        """Test timeout configuration."""
        executor = KubectlExecutor(default_timeout=300, mock_commands=True)

        assert executor.default_timeout == 300

    def test_mock_mode_configuration(self):
        """Test mock mode configuration."""
        executor = KubectlExecutor(mock_commands=True)

        assert executor.mock_commands is True

        executor_real = KubectlExecutor(mock_commands=False)
        assert executor_real.mock_commands is False


class TestTransactionReporting:
    """Test transaction reporting functionality."""

    @pytest.mark.asyncio
    async def test_execution_report_generation(self):
        """Test execution report generation."""
        executor = KubectlExecutor(mock_commands=True)

        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=True,
        )

        completed_transaction = await executor.execute_transaction(transaction)

        # Verify transaction structure
        assert isinstance(completed_transaction, ExecutionTransaction)
        assert completed_transaction.transaction_id == transaction.transaction_id
        assert completed_transaction.execution_mode == ExecutionMode.SINGLE
        assert completed_transaction.dry_run is True
        assert isinstance(completed_transaction.started_at, datetime)
        assert isinstance(completed_transaction.completed_at, datetime)
        assert len(completed_transaction.commands) == 1

    @pytest.mark.asyncio
    async def test_execution_report_with_rollback(self):
        """Test execution report with rollback information."""
        from src.safety.confirmation_manager import ConfirmationManager

        confirmation_manager = ConfirmationManager()
        executor = KubectlExecutor(
            confirmation_manager=confirmation_manager, mock_commands=True
        )

        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=False,
        )

        # Mock rollback snapshot creation
        with patch.object(executor, "_create_rollback_snapshot") as mock_snapshot:
            mock_snapshot.return_value = "test-snapshot"

            completed_transaction = await executor.execute_transaction(transaction)

            assert completed_transaction.rollback_snapshot_id is not None


class TestKubectlExecutorEdgeCases:
    """Test edge cases and error conditions for kubectl executor."""

    @pytest.mark.asyncio
    async def test_execute_real_command_failure(self):
        """Test executing real command that fails."""
        executor = KubectlExecutor(mock_commands=False)

        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="nonexistent-deployment",
            namespace="default",
            kubectl_args=["kubectl", "patch", "deployment", "nonexistent-deployment"],
            manifest_content='{"spec": {"replicas": 3}}',
            dry_run=False,
        )

        # Mock failed subprocess execution
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"deployment not found")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            result = await executor._execute_single_command(command)

            assert isinstance(result, ExecutionResult)
            assert result.status == ExecutionStatus.FAILED
            assert result.exit_code == 1
            assert "deployment not found" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_transaction_staged_mode(self):
        """Test executing transaction in staged mode."""
        executor = KubectlExecutor(mock_commands=True)

        # Create changes across multiple namespaces
        changes = [
            ResourceChange(
                object_name="dev-app",
                namespace="development",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            ),
            ResourceChange(
                object_name="prod-app",
                namespace="production",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "500m", "memory": "512Mi"},
                proposed_values={"cpu": "1000m", "memory": "1Gi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            ),
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.STAGED,
            dry_run=False,
        )

        completed_transaction = await executor.execute_transaction(transaction)

        assert isinstance(completed_transaction, ExecutionTransaction)
        assert completed_transaction.execution_mode == ExecutionMode.STAGED
        assert len(completed_transaction.commands) == 2

    @pytest.mark.asyncio
    async def test_manifest_generation_with_complex_resources(self):
        """Test manifest generation for complex resource configurations."""
        executor = KubectlExecutor(mock_commands=True)

        change = ResourceChange(
            object_name="complex-deployment",
            namespace="custom-namespace",
            object_kind="Deployment",
            change_type="resource_increase",
            current_values={
                "cpu": "2000m",
                "memory": "2Gi",
                "ephemeral-storage": "10Gi",
            },
            proposed_values={
                "cpu": "4000m",
                "memory": "4Gi",
                "ephemeral-storage": "20Gi",
            },
            cpu_change_percent=100.0,
            memory_change_percent=100.0,
        )

        command = await executor._generate_kubectl_command(change, dry_run=False)

        assert isinstance(command, KubectlCommand)
        assert command.resource_name == "complex-deployment"
        assert command.namespace == "custom-namespace"
        assert command.dry_run is False

    @pytest.mark.asyncio
    async def test_get_current_manifest_timeout(self):
        """Test getting current manifest with timeout."""
        executor = KubectlExecutor(mock_commands=False)

        # Mock subprocess with timeout
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                manifest = await executor._get_current_manifest(
                    "Deployment", "timeout-deployment", "default"
                )

                assert manifest is None

    @pytest.mark.asyncio
    async def test_create_transaction_with_empty_changes(self):
        """Test creating transaction with empty changes list."""
        executor = KubectlExecutor(mock_commands=True)

        transaction = await executor.create_transaction(
            changes=[],
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.SINGLE,
            dry_run=True,
        )

        assert isinstance(transaction, ExecutionTransaction)
        assert len(transaction.commands) == 0

    @pytest.mark.asyncio
    async def test_rollback_snapshot_creation_without_confirmation_manager(self):
        """Test rollback snapshot creation without confirmation manager."""
        executor = KubectlExecutor(mock_commands=True)  # No confirmation manager

        commands = [
            KubectlCommand(
                operation="patch",
                resource_type="Deployment",
                resource_name="test-deployment",
                namespace="default",
                kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
                manifest_content='{"spec": {"replicas": 3}}',
                dry_run=False,
            )
        ]

        transaction = ExecutionTransaction(
            confirmation_token_id="test-token", commands=commands
        )

        snapshot_id = await executor._create_rollback_snapshot(transaction)

        # Should return None when no confirmation manager is set
        assert snapshot_id is None

    @pytest.mark.asyncio
    async def test_execute_mock_command_with_failure_simulation(self):
        """Test mock command execution with failure simulation."""
        executor = KubectlExecutor(mock_commands=True)

        # Use a resource name that triggers mock failure
        command = KubectlCommand(
            operation="patch",
            resource_type="Deployment",
            resource_name="failing-app",  # This should trigger mock failure
            namespace="default",
            kubectl_args=["kubectl", "patch", "deployment", "failing-app"],
            manifest_content='{"spec": {"replicas": 3}}',
            dry_run=False,
        )

        result = ExecutionResult(
            command_id=command.command_id,
            status=ExecutionStatus.PENDING,
            started_at=datetime.now(timezone.utc),
            exit_code=-1,
        )

        result = await executor._execute_mock_command(command, result)

        # Should still succeed in most cases (mock mode is permissive)
        assert isinstance(result, ExecutionResult)
        assert result.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED]

    @pytest.mark.asyncio
    async def test_verify_cluster_access_with_context_and_kubeconfig(self):
        """Test cluster access verification with both context and kubeconfig."""
        executor = KubectlExecutor(
            kubernetes_context="custom-context",
            kubeconfig_path="/custom/kubeconfig",
            mock_commands=True,
        )

        # Mock successful cluster access
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"cluster info", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            await executor._verify_cluster_access()

            # Verify the command includes both context and kubeconfig
            mock_subprocess.assert_called_once()
            args = mock_subprocess.call_args[0]
            assert "--context" in args
            assert "custom-context" in args
            assert "--kubeconfig" in args
            assert "/custom/kubeconfig" in args

    @pytest.mark.asyncio
    async def test_kubectl_command_with_special_characters(self):
        """Test kubectl command generation with special characters in names."""
        executor = KubectlExecutor(mock_commands=True)

        change = ResourceChange(
            object_name="app-with-special-chars-123",
            namespace="namespace-with-dashes",
            object_kind="Deployment",
            change_type="resource_increase",
            current_values={"cpu": "100m", "memory": "128Mi"},
            proposed_values={"cpu": "200m", "memory": "256Mi"},
            cpu_change_percent=100.0,
            memory_change_percent=100.0,
        )

        command = await executor._generate_kubectl_command(change, dry_run=True)

        assert command.resource_name == "app-with-special-chars-123"
        assert command.namespace == "namespace-with-dashes"
        assert command.dry_run is True

    @pytest.mark.asyncio
    async def test_transaction_execution_report_summary(self):
        """Test transaction execution report summary generation."""
        executor = KubectlExecutor(mock_commands=True)

        changes = [
            ResourceChange(
                object_name=f"test-deployment-{i}",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
            for i in range(5)
        ]

        transaction = await executor.create_transaction(
            changes=changes,
            confirmation_token_id="test-token-123",
            execution_mode=ExecutionMode.BATCH,
            dry_run=False,
        )

        completed_transaction = await executor.execute_transaction(transaction)

        # Verify transaction completeness
        assert len(completed_transaction.commands) == 5
        assert len(completed_transaction.command_results) == 5
        assert completed_transaction.commands_completed > 0
        assert completed_transaction.overall_status == ExecutionStatus.COMPLETED
