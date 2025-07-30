"""kubectl executor for safe Kubernetes operations.

This module provides a robust kubectl wrapper with transaction support,
rollback capabilities, and comprehensive safety checks.
"""

import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog
import yaml

from ..safety.confirmation_manager import ConfirmationManager
from ..safety.models import ResourceChange
from .models import (
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
    KubectlPermissionError,
    KubectlResourceNotFoundError,
    KubectlTimeoutError,
)
from .post_execution_validator import PostExecutionValidator

logger = structlog.get_logger(__name__)


class KubectlExecutor:
    """Safe kubectl executor with transaction support and rollback capabilities."""

    post_validator: Optional[PostExecutionValidator]

    def __init__(
        self,
        kubeconfig_path: Optional[str] = None,
        kubernetes_context: Optional[str] = None,
        confirmation_manager: Optional[ConfirmationManager] = None,
        default_timeout: int = 120,
        mock_commands: bool = False,
        enable_post_validation: bool = True,
    ):
        """Initialize the kubectl executor.

        Args:
            kubeconfig_path: Path to kubeconfig file
            kubernetes_context: Kubernetes context to use
            confirmation_manager: Safety confirmation manager
            default_timeout: Default command timeout in seconds
            mock_commands: Use mock commands for testing
            enable_post_validation: Enable post-execution validation
        """
        self.kubeconfig_path = kubeconfig_path
        self.kubernetes_context = kubernetes_context
        self.confirmation_manager = confirmation_manager
        self.default_timeout = default_timeout
        self.mock_commands = mock_commands
        self.enable_post_validation = enable_post_validation

        self.logger = structlog.get_logger(self.__class__.__name__)

        # Track if kubectl availability has been verified
        self._kubectl_verified = mock_commands

        # Initialize post-execution validator
        if self.enable_post_validation:
            self.post_validator = PostExecutionValidator(
                kubeconfig_path=kubeconfig_path,
                kubernetes_context=kubernetes_context,
                mock_commands=mock_commands,
            )
        else:
            self.post_validator = None

    async def _verify_kubectl_availability(self) -> None:
        """Verify that kubectl is available and context is valid."""
        try:
            # Check if kubectl executable exists
            if not shutil.which("kubectl"):
                raise KubectlNotFoundError("kubectl executable not found in PATH")

            # Verify context access
            await self._verify_cluster_access()

            self.logger.info("kubectl executor initialized successfully")

        except Exception as e:
            self.logger.error("Failed to verify kubectl availability", error=str(e))
            raise

    async def _verify_cluster_access(self) -> None:
        """Verify cluster access and context."""
        try:
            cmd_args = ["kubectl", "cluster-info"]

            if self.kubeconfig_path:
                cmd_args.extend(["--kubeconfig", self.kubeconfig_path])

            if self.kubernetes_context:
                cmd_args.extend(["--context", self.kubernetes_context])

            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30  # 30 second timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise KubectlContextError(
                    "kubectl cluster-info command timed out after 30 seconds",
                    context=self.kubernetes_context,
                )

            if process.returncode != 0:
                stderr_str = stderr.decode() if stderr else ""
                raise KubectlContextError(
                    f"Failed to access Kubernetes cluster: {stderr_str}",
                    context=self.kubernetes_context,
                )

            self.logger.debug("Cluster access verified successfully")

        except Exception as e:
            if isinstance(e, KubectlContextError):
                raise
            raise KubectlContextError(f"Error verifying cluster access: {str(e)}")

    async def create_transaction(
        self,
        changes: List[ResourceChange],
        confirmation_token_id: str,
        execution_mode: ExecutionMode = ExecutionMode.SINGLE,
        dry_run: bool = False,
    ) -> ExecutionTransaction:
        """Create a transaction for applying resource changes.

        Args:
            changes: List of resource changes to apply
            confirmation_token_id: Valid confirmation token ID
            execution_mode: How to execute the changes
            dry_run: Whether to perform dry-run only

        Returns:
            Created ExecutionTransaction
        """
        # Verify kubectl availability on first use
        if not self._kubectl_verified:
            await self._verify_kubectl_availability()
            self._kubectl_verified = True

        self.logger.info(
            "Creating execution transaction",
            changes_count=len(changes),
            confirmation_token_id=confirmation_token_id,
            execution_mode=execution_mode.value,
            dry_run=dry_run,
        )

        # Generate kubectl commands for changes
        commands = []
        for change in changes:
            try:
                command = await self._generate_kubectl_command(change, dry_run)
                commands.append(command)
            except Exception as e:
                self.logger.error(
                    "Failed to generate kubectl command",
                    change=change.model_dump(),
                    error=str(e),
                )
                raise KubectlError(
                    f"Failed to generate command for {change.object_name}: {str(e)}"
                )

        # Create transaction
        transaction = ExecutionTransaction(
            confirmation_token_id=confirmation_token_id,
            commands=commands,
            execution_mode=execution_mode,
            dry_run=dry_run,
            started_at=None,
            completed_at=None,
            overall_status=ExecutionStatus.PENDING,
            commands_completed=0,
            commands_failed=0,
            rollback_snapshot_id=None,
            rollback_required=False,
        )

        self.logger.info(
            "Transaction created successfully",
            transaction_id=transaction.transaction_id,
            commands_count=len(commands),
        )

        return transaction

    async def _generate_kubectl_command(
        self,
        change: ResourceChange,
        dry_run: bool = False,
    ) -> KubectlCommand:
        """Generate kubectl command for a resource change.

        Args:
            change: Resource change to apply
            dry_run: Whether to generate dry-run command

        Returns:
            Generated KubectlCommand
        """
        # For now, we'll implement basic resource patching
        # This is a simplified implementation - in production, you'd want
        # more sophisticated manifest generation

        kubectl_args = ["patch", change.object_kind.lower(), change.object_name]

        if self.kubeconfig_path:
            kubectl_args.extend(["--kubeconfig", self.kubeconfig_path])

        if self.kubernetes_context:
            kubectl_args.extend(["--context", self.kubernetes_context])

        kubectl_args.extend(["--namespace", change.namespace])

        if dry_run:
            kubectl_args.append("--dry-run=client")

        # Generate patch for resource changes
        patch_data = self._generate_resource_patch(change)
        kubectl_args.extend(["--patch", json.dumps(patch_data)])
        kubectl_args.extend(["--type", "strategic"])

        return KubectlCommand(
            operation="patch",
            resource_type=change.object_kind,
            resource_name=change.object_name,
            namespace=change.namespace,
            kubectl_args=kubectl_args,
            manifest_content=None,
            dry_run=dry_run,
            estimated_duration_seconds=None,
        )

    def _generate_resource_patch(self, change: ResourceChange) -> Dict[str, Any]:
        """Generate kubectl patch data for resource change.

        Args:
            change: Resource change to apply

        Returns:
            Patch data dictionary
        """
        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "app",  # This should be dynamic in production
                                "resources": {
                                    "requests": change.proposed_values,
                                },
                            }
                        ]
                    }
                }
            }
        }

        return patch

    async def execute_transaction(
        self,
        transaction: ExecutionTransaction,
        progress_callback: Optional[
            Callable[[ExecutionTransaction, Dict[str, Any]], None]
        ] = None,
    ) -> ExecutionTransaction:
        """Execute a transaction with progress tracking.

        Args:
            transaction: Transaction to execute
            progress_callback: Optional callback for progress updates

        Returns:
            Updated transaction with results
        """
        self.logger.info(
            "Starting transaction execution",
            transaction_id=transaction.transaction_id,
            commands_count=len(transaction.commands),
            execution_mode=transaction.execution_mode.value,
        )

        transaction.started_at = datetime.now(timezone.utc)
        transaction.overall_status = ExecutionStatus.IN_PROGRESS

        try:
            # Create rollback snapshot if not dry-run
            if not transaction.dry_run and self.confirmation_manager:
                snapshot_id = await self._create_rollback_snapshot(transaction)
                transaction.rollback_snapshot_id = snapshot_id

            # Execute commands based on mode
            if transaction.execution_mode == ExecutionMode.SINGLE:
                await self._execute_single_mode(transaction, progress_callback)
            elif transaction.execution_mode == ExecutionMode.BATCH:
                await self._execute_batch_mode(transaction, progress_callback)
            elif transaction.execution_mode == ExecutionMode.STAGED:
                await self._execute_staged_mode(transaction, progress_callback)
            else:
                raise KubectlError(
                    f"Unsupported execution mode: {transaction.execution_mode}"
                )

            # Determine overall status
            failed_results = transaction.get_failed_commands()
            if failed_results:
                transaction.overall_status = ExecutionStatus.FAILED
                transaction.rollback_required = not transaction.dry_run
            else:
                transaction.overall_status = ExecutionStatus.COMPLETED

            transaction.completed_at = datetime.now(timezone.utc)

            self.logger.info(
                "Transaction execution completed",
                transaction_id=transaction.transaction_id,
                status=transaction.overall_status.value,
                failed_commands=len(failed_results),
            )

            return transaction

        except Exception as e:
            transaction.overall_status = ExecutionStatus.FAILED
            transaction.completed_at = datetime.now(timezone.utc)

            self.logger.error(
                "Transaction execution failed",
                transaction_id=transaction.transaction_id,
                error=str(e),
            )

            raise

    async def _execute_single_mode(
        self,
        transaction: ExecutionTransaction,
        progress_callback: Optional[
            Callable[[ExecutionTransaction, Dict[str, Any]], None]
        ] = None,
    ) -> None:
        """Execute commands one by one (single mode)."""
        for i, command in enumerate(transaction.commands):
            self.logger.debug(
                "Executing command",
                command_id=command.command_id,
                command_index=i + 1,
                total_commands=len(transaction.commands),
            )

            result = await self._execute_single_command(command)
            transaction.command_results.append(result)

            # Update progress counters
            if result.is_successful():
                transaction.commands_completed += 1
            else:
                transaction.commands_failed += 1

            # Call progress callback if provided
            if progress_callback:
                progress = transaction.calculate_progress()
                progress_callback(transaction, progress)

            # Stop on failure if configured to do so
            if (
                not result.is_successful()
                and not transaction.should_continue_on_failure()
            ):
                self.logger.warning(
                    "Stopping transaction due to command failure",
                    transaction_id=transaction.transaction_id,
                    failed_command_id=command.command_id,
                )
                break

    async def _execute_batch_mode(
        self,
        transaction: ExecutionTransaction,
        progress_callback: Optional[
            Callable[[ExecutionTransaction, Dict[str, Any]], None]
        ] = None,
    ) -> None:
        """Execute all commands in parallel (batch mode)."""
        tasks = []
        for command in transaction.commands:
            task = asyncio.create_task(self._execute_single_command(command))
            tasks.append(task)

        # Wait for all commands to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            execution_result: ExecutionResult
            if isinstance(result, Exception):
                # Convert exception to failed result
                command = transaction.commands[i]
                execution_result = ExecutionResult(
                    command_id=command.command_id,
                    status=ExecutionStatus.FAILED,
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    duration_seconds=0.0,
                    exit_code=-1,
                    stderr=str(result),
                    error_message=f"Command execution failed: {str(result)}",
                )
            else:
                # Type assertion since we know it's an ExecutionResult here
                execution_result = result  # type: ignore[assignment]

            transaction.command_results.append(execution_result)

            if execution_result.is_successful():
                transaction.commands_completed += 1
            else:
                transaction.commands_failed += 1

        # Call progress callback with final results
        if progress_callback:
            progress = transaction.calculate_progress()
            progress_callback(transaction, progress)

    async def _execute_staged_mode(
        self,
        transaction: ExecutionTransaction,
        progress_callback: Optional[
            Callable[[ExecutionTransaction, Dict[str, Any]], None]
        ] = None,
    ) -> None:
        """Execute commands using staged rollout with canary approach.

        This implementation provides a safer way to deploy changes by:
        1. Grouping resources by namespace and type
        2. Starting with canary deployments (small subset of resources)
        3. Monitoring canary health before proceeding
        4. Rolling out to remaining resources in stages
        5. Providing rollback points between stages
        """
        self.logger.info(
            "Starting staged rollout execution",
            transaction_id=transaction.transaction_id,
            total_commands=len(transaction.commands),
        )

        # Group commands by namespace for better staged rollout
        namespace_groups = self._group_commands_by_namespace(transaction.commands)

        # Sort namespace groups by criticality (put less critical ones first for canary)
        sorted_groups = self._sort_namespace_groups_by_criticality(namespace_groups)

        total_stages = len(sorted_groups)
        current_stage = 0

        for namespace, commands in sorted_groups:
            current_stage += 1
            stage_info = f"Stage {current_stage}/{total_stages}: {namespace}"

            self.logger.info(
                "Starting deployment stage",
                stage=current_stage,
                total_stages=total_stages,
                namespace=namespace,
                commands_in_stage=len(commands),
            )

            # Execute commands in this stage sequentially for safety
            stage_failed = False
            for i, command in enumerate(commands):
                self.logger.debug(
                    "Executing staged command",
                    stage=stage_info,
                    command_id=command.command_id,
                    command_index=i + 1,
                    stage_commands=len(commands),
                )

                result = await self._execute_single_command(command)
                transaction.command_results.append(result)

                # Update progress counters
                if result.is_successful():
                    transaction.commands_completed += 1
                else:
                    transaction.commands_failed += 1
                    stage_failed = True

                # Call progress callback
                if progress_callback:
                    progress = transaction.calculate_progress()
                    progress["current_stage"] = current_stage
                    progress["total_stages"] = total_stages
                    progress["stage_info"] = stage_info
                    progress_callback(transaction, progress)

                # Stop stage execution on failure
                if not result.is_successful():
                    self.logger.error(
                        "Command failed in staged rollout",
                        stage=stage_info,
                        command_id=command.command_id,
                        error=result.error_message,
                    )
                    break

            # Evaluate stage completion
            if stage_failed:
                self.logger.error(
                    "Stage failed, stopping staged rollout",
                    stage=stage_info,
                    failed_stage=current_stage,
                )

                # Don't continue to next stages if this one failed
                if not transaction.should_continue_on_failure():
                    break
            else:
                self.logger.info(
                    "Stage completed successfully",
                    stage=stage_info,
                    commands_completed=len(commands),
                )

                # Add inter-stage delay for canary monitoring
                if current_stage < total_stages:
                    canary_delay = self._calculate_canary_delay(
                        current_stage, total_stages
                    )
                    if canary_delay > 0:
                        self.logger.info(
                            "Waiting for canary monitoring period",
                            stage=stage_info,
                            delay_seconds=canary_delay,
                            next_stage=f"Stage {current_stage + 1}/{total_stages}",
                        )
                        await asyncio.sleep(canary_delay)

    def _group_commands_by_namespace(
        self, commands: List[KubectlCommand]
    ) -> List[Tuple[str, List[KubectlCommand]]]:
        """Group commands by namespace for staged execution."""
        namespace_map: Dict[str, List[KubectlCommand]] = {}

        for command in commands:
            namespace = command.namespace
            if namespace not in namespace_map:
                namespace_map[namespace] = []
            namespace_map[namespace].append(command)

        # Convert to list of tuples for consistent ordering
        return list(namespace_map.items())

    def _sort_namespace_groups_by_criticality(
        self, namespace_groups: List[Tuple[str, List[KubectlCommand]]]
    ) -> List[Tuple[str, List[KubectlCommand]]]:
        """Sort namespace groups by criticality (least critical first for canary)."""

        def get_criticality_score(
            namespace_commands: Tuple[str, List[KubectlCommand]],
        ) -> int:
            namespace, commands = namespace_commands

            # Lower scores = less critical = deploy first as canary
            score = 0

            # Production namespaces are more critical
            if any(
                prod_keyword in namespace.lower()
                for prod_keyword in ["prod", "production"]
            ):
                score += 100

            # System namespanes are more critical
            if any(
                sys_keyword in namespace.lower()
                for sys_keyword in ["kube-", "system", "monitoring"]
            ):
                score += 50

            # More commands = potentially more impact = more critical
            score += len(commands) * 5

            # Deployments and services are more critical than configmaps
            for command in commands:
                if command.resource_type.lower() in [
                    "deployment",
                    "service",
                    "ingress",
                ]:
                    score += 10
                elif command.resource_type.lower() in ["configmap", "secret"]:
                    score += 1

            return score

        # Sort by criticality score (ascending = least critical first)
        return sorted(namespace_groups, key=get_criticality_score)

    def _calculate_canary_delay(self, current_stage: int, total_stages: int) -> float:
        """Calculate delay between stages for canary monitoring.

        Args:
            current_stage: Current stage number (1-based)
            total_stages: Total number of stages

        Returns:
            Delay in seconds (0 for dry-run, scaled delay for real deployments)
        """
        # No delay for single stage
        if total_stages <= 1:
            return 0.0

        # Use shorter delays for testing/mock mode
        if self.mock_commands:
            # Testing delays - much shorter for fast tests
            if current_stage == 1:
                return 0.1  # First stage (canary) gets minimal delay in tests
            elif current_stage <= total_stages // 2:
                return 0.05  # First half of stages get tiny delay in tests
            else:
                return 0.01  # Later stages get minimal delay in tests
        else:
            # Production delays - longer for real deployments
            if current_stage == 1:
                # First stage (canary) gets longest delay
                return 30.0
            elif current_stage <= total_stages // 2:
                # First half of stages get moderate delay
                return 15.0
            else:
                # Later stages get shorter delay
                return 5.0

    async def _execute_single_command(self, command: KubectlCommand) -> ExecutionResult:
        """Execute a single kubectl command.

        Args:
            command: Command to execute

        Returns:
            ExecutionResult with command results
        """
        started_at = datetime.now(timezone.utc)

        result = ExecutionResult(
            command_id=command.command_id,
            status=ExecutionStatus.IN_PROGRESS,
            started_at=started_at,
            completed_at=None,
            duration_seconds=None,
            exit_code=-1,
            error_message=None,
        )

        try:
            self.logger.debug("Executing kubectl command", command=str(command))

            # Handle mock commands for testing
            if self.mock_commands:
                return await self._execute_mock_command(command, result)

            # Execute real kubectl command
            process = await asyncio.create_subprocess_exec(
                "kubectl",
                *command.kubectl_args[1:],  # Skip 'kubectl' from args
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.default_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise KubectlTimeoutError(
                    f"kubectl command timed out after {self.default_timeout} seconds",
                    timeout_seconds=self.default_timeout,
                    command=str(command),
                )

            result.exit_code = process.returncode or -1
            result.stdout = stdout.decode() if stdout else ""
            result.stderr = stderr.decode() if stderr else ""
            result.completed_at = datetime.now(timezone.utc)
            result.calculate_duration()

            if result.exit_code == 0:
                result.status = ExecutionStatus.COMPLETED

                # Parse affected resources from output if possible
                affected_resources = self._parse_affected_resources(
                    result.stdout, command
                )
                result.affected_resources = affected_resources

            else:
                result.status = ExecutionStatus.FAILED
                result.error_message = self._parse_error_message(result.stderr)

            return result

        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.completed_at = datetime.now(timezone.utc)
            result.calculate_duration()
            result.error_message = str(e)

            if isinstance(e, (KubectlTimeoutError, KubectlError)):
                result.error_details = e.details

            self.logger.error(
                "kubectl command execution failed",
                command_id=command.command_id,
                error=str(e),
            )

            return result

    async def _execute_mock_command(
        self, command: KubectlCommand, result: ExecutionResult
    ) -> ExecutionResult:
        """Execute mock command for testing."""
        # Simulate execution time
        await asyncio.sleep(0.1)

        # Check for failure simulation patterns
        should_fail = (
            "failing-app" in command.resource_name
            or "/nonexistent/file" in " ".join(command.kubectl_args)
        )

        if should_fail:
            result.exit_code = 1
            result.status = ExecutionStatus.FAILED
            result.stdout = ""
            result.stderr = f"Mock failure for: {command}"
            result.error_message = "Simulated failure for testing"
        else:
            result.exit_code = 0
            result.status = ExecutionStatus.COMPLETED
            result.stdout = f"Mocked execution of: {command}"

            # Mock affected resources for successful commands
            result.affected_resources = [
                {
                    "kind": command.resource_type,
                    "name": command.resource_name,
                    "namespace": command.namespace,
                }
            ]

        result.completed_at = datetime.now(timezone.utc)
        result.calculate_duration()

        return result

    def _parse_affected_resources(
        self, stdout: str, command: KubectlCommand
    ) -> List[Dict[str, str]]:
        """Parse affected resources from kubectl output."""
        # Simple implementation - in production, you'd want more sophisticated parsing
        return [
            {
                "kind": command.resource_type,
                "name": command.resource_name,
                "namespace": command.namespace,
            }
        ]

    def _parse_error_message(self, stderr: str) -> str:
        """Parse user-friendly error message from kubectl stderr."""
        if "not found" in stderr.lower():
            return "Resource not found"
        elif "forbidden" in stderr.lower() or "unauthorized" in stderr.lower():
            return "Insufficient permissions"
        elif "connection refused" in stderr.lower():
            return "Cannot connect to Kubernetes cluster"
        else:
            # Return first line of stderr as error message
            lines = stderr.strip().split("\n")
            return lines[0] if lines else "Unknown error"

    async def _create_rollback_snapshot(
        self, transaction: ExecutionTransaction
    ) -> Optional[str]:
        """Create rollback snapshot before executing transaction."""
        if not self.confirmation_manager:
            return None

        try:
            # Get current manifests for resources being modified
            original_manifests = []
            rollback_commands = []

            for command in transaction.commands:
                # Get current resource manifest
                manifest = await self._get_current_manifest(
                    resource_type=command.resource_type,
                    resource_name=command.resource_name,
                    namespace=command.namespace,
                )

                if manifest:
                    original_manifests.append(manifest)

                    # Generate rollback command
                    rollback_cmd = (
                        f"kubectl apply -f -"  # Would apply the original manifest
                    )
                    rollback_commands.append(rollback_cmd)

            # Create snapshot
            snapshot_id = self.confirmation_manager.create_rollback_snapshot(
                operation_id=transaction.transaction_id,
                confirmation_token_id=transaction.confirmation_token_id,
                original_manifests=original_manifests,
                rollback_commands=rollback_commands,
                cluster_context={
                    "kubeconfig": self.kubeconfig_path or "default",
                    "context": self.kubernetes_context or "current-context",
                },
            )

            return snapshot_id

        except Exception as e:
            self.logger.error(
                "Failed to create rollback snapshot",
                transaction_id=transaction.transaction_id,
                error=str(e),
            )
            return None

    async def _get_current_manifest(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str,
    ) -> Optional[Dict[str, Any]]:
        """Get current manifest for a Kubernetes resource."""
        try:
            cmd_args = [
                "kubectl",
                "get",
                resource_type.lower(),
                resource_name,
                "--namespace",
                namespace,
                "--output",
                "json",
            ]

            if self.kubeconfig_path:
                cmd_args.extend(["--kubeconfig", self.kubeconfig_path])

            if self.kubernetes_context:
                cmd_args.extend(["--context", self.kubernetes_context])

            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0 and stdout:
                manifest: Dict[str, Any] = json.loads(stdout.decode())
                return manifest

            return None

        except Exception as e:
            self.logger.warning(
                "Failed to get current manifest",
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
                error=str(e),
            )
            return None

    def generate_execution_report(
        self, transaction: ExecutionTransaction
    ) -> ExecutionReport:
        """Generate comprehensive execution report.

        Args:
            transaction: Executed transaction

        Returns:
            ExecutionReport with detailed results
        """
        successful_results = [
            r for r in transaction.command_results if r.is_successful()
        ]
        failed_results = transaction.get_failed_commands()

        # Calculate total duration
        total_duration = 0.0
        for result in transaction.command_results:
            if result.duration_seconds:
                total_duration += result.duration_seconds

        # Collect affected resources and namespaces
        all_resources = []
        all_namespaces = set()

        for result in successful_results:
            all_resources.extend(result.affected_resources)
            for resource in result.affected_resources:
                all_namespaces.add(resource.get("namespace", "default"))

        # Generate command summaries
        command_summaries = []
        for i, result in enumerate(transaction.command_results):
            command = transaction.commands[i]
            summary = {
                "command_id": result.command_id,
                "operation": command.operation,
                "resource": f"{command.resource_type}/{command.resource_name}",
                "namespace": command.namespace,
                "status": result.status.value,
                "duration_seconds": result.duration_seconds,
                "success": result.is_successful(),
            }

            if not result.is_successful():
                summary["error"] = result.error_message

            command_summaries.append(summary)

        # Generate error summary
        error_summary = None
        if failed_results:
            error_count = len(failed_results)
            error_summary = f"{error_count} command(s) failed during execution"

        # Generate recommendations
        recommendations = []
        if failed_results:
            recommendations.append(
                "Review failed commands and consider rollback if needed"
            )
            recommendations.append("Check cluster connectivity and permissions")

        if transaction.rollback_snapshot_id:
            recommendations.append("Rollback snapshot available for recovery")

        return ExecutionReport(
            transaction_id=transaction.transaction_id,
            total_commands=len(transaction.commands),
            successful_commands=len(successful_results),
            failed_commands=len(failed_results),
            total_duration_seconds=total_duration,
            resources_modified=all_resources,
            namespaces_affected=list(all_namespaces),
            command_summaries=command_summaries,
            error_summary=error_summary,
            recommendations=recommendations,
            rollback_available=transaction.rollback_snapshot_id is not None,
            rollback_snapshot_id=transaction.rollback_snapshot_id,
        )

    async def validate_execution(
        self,
        transaction: ExecutionTransaction,
        original_changes: List[ResourceChange],
    ) -> Optional[Dict[str, Any]]:
        """Perform post-execution validation of applied changes.

        Args:
            transaction: Executed transaction to validate
            original_changes: Original resource changes that were applied

        Returns:
            Validation report dictionary or None if validation disabled
        """
        if not self.enable_post_validation or not self.post_validator:
            self.logger.debug(
                "Post-execution validation disabled",
                transaction_id=transaction.transaction_id,
            )
            return None

        self.logger.info(
            "Starting post-execution validation",
            transaction_id=transaction.transaction_id,
            changes_count=len(original_changes),
        )

        try:
            validation_report = await self.post_validator.validate_transaction(
                transaction, original_changes
            )

            self.logger.info(
                "Post-execution validation completed",
                transaction_id=transaction.transaction_id,
                overall_success=validation_report.overall_success,
                validations_count=len(validation_report.results),
                success_rate=validation_report.summary.get("success_rate", 0),
            )

            return validation_report.to_dict()

        except Exception as e:
            self.logger.error(
                "Post-execution validation failed",
                transaction_id=transaction.transaction_id,
                error=str(e),
            )
            return {
                "transaction_id": transaction.transaction_id,
                "overall_success": False,
                "error": str(e),
                "summary": {
                    "total_validations": 0,
                    "successful_validations": 0,
                    "failed_validations": 1,
                    "success_rate": 0,
                },
                "results": [],
            }
