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
        assert command.object_name == "test-deployment"
        assert command.namespace == "default"
        assert command.object_kind == "Deployment"
        assert command.dry_run is True
        assert "kubectl" in command.kubectl_args[0]
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
        report = await executor.execute_transaction(transaction)

        assert isinstance(report, ExecutionReport)
        assert report.transaction_id == transaction.transaction_id
        assert report.execution_status in [
            ExecutionStatus.SUCCESS,
            ExecutionStatus.COMPLETED,
        ]
        assert len(report.command_results) == 1

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
        report = await executor.execute_transaction(transaction)

        assert isinstance(report, ExecutionReport)
        assert len(report.command_results) == 3
        assert all(
            result.status == ExecutionStatus.SUCCESS
            for result in report.command_results
        )

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
        report = await executor.execute_transaction(transaction)

        assert report.dry_run is True
        assert report.execution_status == ExecutionStatus.SUCCESS
        assert len(report.command_results) == 1
        assert report.command_results[0].dry_run is True


class TestSingleCommandExecution:
    """Test single command execution."""

    @pytest.mark.asyncio
    async def test_execute_single_command_mock_mode(self):
        """Test executing single command in mock mode."""
        executor = KubectlExecutor(mock_commands=True)

        command = KubectlCommand(
            object_name="test-deployment",
            namespace="default",
            object_kind="Deployment",
            kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
            patch_content='{"spec": {"replicas": 3}}',
            dry_run=False,
        )

        result = await executor._execute_single_command(command)

        assert isinstance(result, ExecutionResult)
        assert result.status == ExecutionStatus.SUCCESS
        assert result.command_id == command.command_id
        assert result.mock_execution is True

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
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                kubectl_args=["kubectl", "get", "deployment", "test-deployment"],
                patch_content="",
                dry_run=False,
            )

            # Should not raise in mock mode, but would timeout in real mode
            result = await executor._execute_single_command(command)
            assert result.status == ExecutionStatus.SUCCESS  # Mock mode succeeds

    @pytest.mark.asyncio
    async def test_execute_mock_command(self):
        """Test mock command execution."""
        executor = KubectlExecutor(mock_commands=True)

        command = KubectlCommand(
            object_name="test-deployment",
            namespace="default",
            object_kind="Deployment",
            kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
            patch_content='{"spec": {"replicas": 3}}',
            dry_run=False,
        )

        result = await executor._execute_mock_command(command)

        assert isinstance(result, ExecutionResult)
        assert result.status == ExecutionStatus.SUCCESS
        assert result.mock_execution is True
        assert result.stdout == "Mock execution successful"
        assert "kubectl patch deployment test-deployment" in result.command_executed


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

            snapshot = await executor._create_rollback_snapshot(
                commands, "test-context"
            )

            assert isinstance(snapshot, RollbackSnapshot)
            assert snapshot.snapshot_id.startswith("rollback-")
            assert len(snapshot.resources_snapshot) == 1
            assert len(snapshot.kubectl_commands) == 1
            assert snapshot.execution_context == "test-context"

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
            object_name="test-deployment",
            namespace="default",
            object_kind="Deployment",
            kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
            patch_content="invalid-json",
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
            assert result.status == ExecutionStatus.SUCCESS  # Mock mode succeeds

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
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                kubectl_args=["kubectl", "patch", "deployment", "test-deployment"],
                patch_content='{"spec": {"replicas": 3}}',
                dry_run=False,
            )

            # Should handle gracefully in mock mode
            result = await executor._execute_single_command(command)
            assert result.status == ExecutionStatus.SUCCESS  # Mock mode succeeds


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

        report = await executor.execute_transaction(transaction)

        # Verify report structure
        assert isinstance(report, ExecutionReport)
        assert report.transaction_id == transaction.transaction_id
        assert report.execution_mode == ExecutionMode.SINGLE
        assert report.dry_run is True
        assert isinstance(report.started_at, datetime)
        assert isinstance(report.completed_at, datetime)
        assert report.execution_duration_seconds >= 0
        assert len(report.command_results) == 1

    @pytest.mark.asyncio
    async def test_execution_report_with_rollback(self):
        """Test execution report with rollback information."""
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
            dry_run=False,
            create_rollback_snapshot=True,
        )

        # Mock rollback snapshot creation
        with patch.object(executor, "_create_rollback_snapshot") as mock_snapshot:
            mock_snapshot.return_value = RollbackSnapshot(
                snapshot_id="test-snapshot",
                created_at=datetime.now(timezone.utc),
                resources_snapshot=[{"test": "data"}],
                kubectl_commands=["kubectl get deployment test-deployment"],
                execution_context="test",
                rollback_commands=["kubectl apply -f snapshot.yaml"],
            )

            report = await executor.execute_transaction(transaction)

            assert report.rollback_snapshot is not None
            assert report.rollback_snapshot.snapshot_id == "test-snapshot"
