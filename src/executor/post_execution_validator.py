"""Post-execution validation for kubectl operations.

This module provides comprehensive validation of executed changes to ensure
they were applied correctly and resources are healthy after modifications.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

from ..safety.models import ResourceChange
from .models import ExecutionResult, ExecutionTransaction, KubectlCommand

logger = structlog.get_logger(__name__)


class ValidationError(Exception):
    """Error during post-execution validation."""

    def __init__(
        self,
        message: str,
        validation_type: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.validation_type = validation_type
        self.details = details or {}


class ValidationResult:
    """Result of post-execution validation."""

    def __init__(
        self,
        validation_type: str,
        resource_type: str,
        resource_name: str,
        namespace: str,
        success: bool,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.validation_type = validation_type
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.namespace = namespace
        self.success = success
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "validation_type": self.validation_type,
            "resource_type": self.resource_type,
            "resource_name": self.resource_name,
            "namespace": self.namespace,
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class ValidationReport:
    """Comprehensive post-execution validation report."""

    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id
        self.started_at = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        self.results: List[ValidationResult] = []
        self.overall_success = True
        self.summary: Dict[str, Any] = {}

    def add_result(self, result: ValidationResult) -> None:
        """Add a validation result."""
        self.results.append(result)
        if not result.success:
            self.overall_success = False

    def complete(self) -> None:
        """Mark validation as completed and generate summary."""
        self.completed_at = datetime.now(timezone.utc)

        # Generate summary statistics
        total_validations = len(self.results)
        successful_validations = len([r for r in self.results if r.success])
        failed_validations = total_validations - successful_validations

        validation_types = set(r.validation_type for r in self.results)

        self.summary = {
            "total_validations": total_validations,
            "successful_validations": successful_validations,
            "failed_validations": failed_validations,
            "success_rate": (
                (successful_validations / total_validations * 100)
                if total_validations > 0
                else 0
            ),
            "validation_types": list(validation_types),
            "duration_seconds": (self.completed_at - self.started_at).total_seconds(),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "transaction_id": self.transaction_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "overall_success": self.overall_success,
            "summary": self.summary,
            "results": [r.to_dict() for r in self.results],
        }


class PostExecutionValidator:
    """Validates changes after kubectl execution."""

    def __init__(
        self,
        kubeconfig_path: Optional[str] = None,
        kubernetes_context: Optional[str] = None,
        mock_commands: bool = False,
        validation_timeout: int = 300,  # 5 minutes
        readiness_wait_time: int = 60,  # 1 minute for pods to become ready
    ):
        """Initialize the post-execution validator.

        Args:
            kubeconfig_path: Path to kubeconfig file
            kubernetes_context: Kubernetes context to use
            mock_commands: Use mock validation for testing
            validation_timeout: Total timeout for validation operations
            readiness_wait_time: Time to wait for pods to become ready
        """
        self.kubeconfig_path = kubeconfig_path
        self.kubernetes_context = kubernetes_context
        self.mock_commands = mock_commands
        self.validation_timeout = validation_timeout
        self.readiness_wait_time = readiness_wait_time

        self.logger = structlog.get_logger(self.__class__.__name__)

    async def validate_transaction(
        self,
        transaction: ExecutionTransaction,
        original_changes: List[ResourceChange],
    ) -> ValidationReport:
        """Validate all changes in a transaction.

        Args:
            transaction: Executed transaction to validate
            original_changes: Original resource changes that were applied

        Returns:
            ValidationReport with comprehensive validation results
        """
        report = ValidationReport(transaction.transaction_id)

        self.logger.info(
            "Starting post-execution validation",
            transaction_id=transaction.transaction_id,
            commands_count=len(transaction.commands),
        )

        try:
            # Only validate successful commands
            successful_results = [
                r for r in transaction.command_results if r.is_successful()
            ]

            if not successful_results:
                self.logger.warning(
                    "No successful commands to validate",
                    transaction_id=transaction.transaction_id,
                )
                report.complete()
                return report

            # Create a mapping of commands to their original changes
            change_map = self._create_change_mapping(
                transaction.commands, original_changes
            )

            # Validate each successful command
            for result in successful_results:
                command = self._find_command_by_id(
                    transaction.commands, result.command_id
                )
                if not command:
                    continue

                original_change = change_map.get(command.command_id)

                # Perform different types of validation
                await self._validate_resource_changes(command, original_change, report)
                await self._validate_resource_health(command, report)
                await self._validate_pod_readiness(command, report)

            # Wait for pods to stabilize and check again
            if not self.mock_commands:
                self.logger.info(
                    "Waiting for pods to stabilize",
                    wait_time=self.readiness_wait_time,
                )
                await asyncio.sleep(self.readiness_wait_time)

            # Check pod stability (for both mock and real modes)
            for result in successful_results:
                command = self._find_command_by_id(
                    transaction.commands, result.command_id
                )
                if command:
                    await self._validate_pod_stability(command, report)

        except Exception as e:
            self.logger.error(
                "Post-execution validation failed",
                transaction_id=transaction.transaction_id,
                error=str(e),
            )
            # Add failure result
            failure_result = ValidationResult(
                validation_type="validation_error",
                resource_type="unknown",
                resource_name="unknown",
                namespace="unknown",
                success=False,
                message=f"Validation process failed: {str(e)}",
                details={"error_type": type(e).__name__},
            )
            report.add_result(failure_result)

        finally:
            report.complete()

            self.logger.info(
                "Post-execution validation completed",
                transaction_id=transaction.transaction_id,
                overall_success=report.overall_success,
                success_rate=report.summary.get("success_rate", 0),
            )

        return report

    def _create_change_mapping(
        self,
        commands: List[KubectlCommand],
        changes: List[ResourceChange],
    ) -> Dict[str, ResourceChange]:
        """Create mapping from command IDs to original resource changes."""
        change_map = {}

        for i, command in enumerate(commands):
            if i < len(changes):
                change_map[command.command_id] = changes[i]

        return change_map

    def _find_command_by_id(
        self,
        commands: List[KubectlCommand],
        command_id: str,
    ) -> Optional[KubectlCommand]:
        """Find command by ID."""
        for command in commands:
            if command.command_id == command_id:
                return command
        return None

    async def _validate_resource_changes(
        self,
        command: KubectlCommand,
        original_change: Optional[ResourceChange],
        report: ValidationReport,
    ) -> None:
        """Validate that resource changes were applied correctly."""
        if self.mock_commands:
            # Mock validation always succeeds
            result = ValidationResult(
                validation_type="resource_changes",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=True,
                message="Mock validation: Resource changes applied successfully",
                details={"mock": True},
            )
            report.add_result(result)
            return

        try:
            # Get current resource state
            current_manifest = await self._get_resource_manifest(
                command.resource_type,
                command.resource_name,
                command.namespace,
            )

            if not current_manifest:
                result = ValidationResult(
                    validation_type="resource_changes",
                    resource_type=command.resource_type,
                    resource_name=command.resource_name,
                    namespace=command.namespace,
                    success=False,
                    message="Resource not found after applying changes",
                )
                report.add_result(result)
                return

            # Extract resource requests from the manifest
            success, message, details = self._verify_resource_requests(
                current_manifest, original_change
            )

            result = ValidationResult(
                validation_type="resource_changes",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=success,
                message=message,
                details=details,
            )
            report.add_result(result)

        except Exception as e:
            result = ValidationResult(
                validation_type="resource_changes",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=False,
                message=f"Failed to validate resource changes: {str(e)}",
                details={"error": str(e)},
            )
            report.add_result(result)

    async def _validate_resource_health(
        self,
        command: KubectlCommand,
        report: ValidationReport,
    ) -> None:
        """Validate that the resource is healthy after changes."""
        if self.mock_commands:
            result = ValidationResult(
                validation_type="resource_health",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=True,
                message="Mock validation: Resource is healthy",
                details={"mock": True},
            )
            report.add_result(result)
            return

        try:
            # Get resource status
            manifest = await self._get_resource_manifest(
                command.resource_type,
                command.resource_name,
                command.namespace,
            )

            if not manifest:
                result = ValidationResult(
                    validation_type="resource_health",
                    resource_type=command.resource_type,
                    resource_name=command.resource_name,
                    namespace=command.namespace,
                    success=False,
                    message="Resource not found for health check",
                )
                report.add_result(result)
                return

            # Check resource-specific health indicators
            success, message, details = self._check_resource_health(
                manifest, command.resource_type
            )

            result = ValidationResult(
                validation_type="resource_health",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=success,
                message=message,
                details=details,
            )
            report.add_result(result)

        except Exception as e:
            result = ValidationResult(
                validation_type="resource_health",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=False,
                message=f"Failed to check resource health: {str(e)}",
                details={"error": str(e)},
            )
            report.add_result(result)

    async def _validate_pod_readiness(
        self,
        command: KubectlCommand,
        report: ValidationReport,
    ) -> None:
        """Validate that pods are ready after resource changes."""
        if self.mock_commands:
            result = ValidationResult(
                validation_type="pod_readiness",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=True,
                message="Mock validation: Pods are ready",
                details={"mock": True, "ready_pods": 2, "total_pods": 2},
            )
            report.add_result(result)
            return

        # Only check pod readiness for resources that control pods
        if command.resource_type.lower() not in [
            "deployment",
            "daemonset",
            "statefulset",
            "replicaset",
        ]:
            return

        try:
            # Get pods controlled by this resource
            pods = await self._get_controlled_pods(
                command.resource_type,
                command.resource_name,
                command.namespace,
            )

            ready_pods = 0
            total_pods = len(pods)
            pod_issues = []

            for pod in pods:
                is_ready, pod_status = self._check_pod_readiness(pod)
                if is_ready:
                    ready_pods += 1
                else:
                    pod_issues.append(
                        {
                            "pod_name": pod.get("metadata", {}).get("name", "unknown"),
                            "status": pod_status,
                        }
                    )

            success = ready_pods == total_pods and total_pods > 0
            message = f"Pod readiness: {ready_pods}/{total_pods} pods ready"

            if not success and pod_issues:
                message += f". Issues: {', '.join([f'{issue['pod_name']}: {issue['status']}' for issue in pod_issues[:3]])}"

            result = ValidationResult(
                validation_type="pod_readiness",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=success,
                message=message,
                details={
                    "ready_pods": ready_pods,
                    "total_pods": total_pods,
                    "pod_issues": pod_issues,
                },
            )
            report.add_result(result)

        except Exception as e:
            result = ValidationResult(
                validation_type="pod_readiness",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=False,
                message=f"Failed to check pod readiness: {str(e)}",
                details={"error": str(e)},
            )
            report.add_result(result)

    async def _validate_pod_stability(
        self,
        command: KubectlCommand,
        report: ValidationReport,
    ) -> None:
        """Validate that pods remain stable after the wait period."""
        if self.mock_commands:
            result = ValidationResult(
                validation_type="pod_stability",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=True,
                message="Mock validation: Pods are stable",
                details={"mock": True, "stable_pods": 2, "total_pods": 2},
            )
            report.add_result(result)
            return

        # Only check pod stability for resources that control pods
        if command.resource_type.lower() not in [
            "deployment",
            "daemonset",
            "statefulset",
            "replicaset",
        ]:
            return

        try:
            # Get pods and check for stability issues
            pods = await self._get_controlled_pods(
                command.resource_type,
                command.resource_name,
                command.namespace,
            )

            stable_pods = 0
            total_pods = len(pods)
            stability_issues = []

            for pod in pods:
                is_stable, stability_status = self._check_pod_stability(pod)
                if is_stable:
                    stable_pods += 1
                else:
                    stability_issues.append(
                        {
                            "pod_name": pod.get("metadata", {}).get("name", "unknown"),
                            "issue": stability_status,
                        }
                    )

            success = stable_pods == total_pods and total_pods > 0
            message = f"Pod stability: {stable_pods}/{total_pods} pods stable"

            if not success and stability_issues:
                message += f". Issues: {', '.join([f'{issue['pod_name']}: {issue['issue']}' for issue in stability_issues[:3]])}"

            result = ValidationResult(
                validation_type="pod_stability",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=success,
                message=message,
                details={
                    "stable_pods": stable_pods,
                    "total_pods": total_pods,
                    "stability_issues": stability_issues,
                },
            )
            report.add_result(result)

        except Exception as e:
            result = ValidationResult(
                validation_type="pod_stability",
                resource_type=command.resource_type,
                resource_name=command.resource_name,
                namespace=command.namespace,
                success=False,
                message=f"Failed to check pod stability: {str(e)}",
                details={"error": str(e)},
            )
            report.add_result(result)

    async def _get_resource_manifest(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str,
    ) -> Optional[Dict[str, Any]]:
        """Get current resource manifest."""
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

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30,
            )

            if process.returncode == 0 and stdout:
                manifest: Dict[str, Any] = json.loads(stdout.decode())
                return manifest

            return None

        except Exception as e:
            self.logger.warning(
                "Failed to get resource manifest",
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
                error=str(e),
            )
            return None

    async def _get_controlled_pods(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str,
    ) -> List[Dict[str, Any]]:
        """Get pods controlled by a resource."""
        try:
            # Get pods with label selector based on resource
            cmd_args = [
                "kubectl",
                "get",
                "pods",
                "--namespace",
                namespace,
                "--selector",
                f"app={resource_name}",  # Simplified selector
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

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30,
            )

            if process.returncode == 0 and stdout:
                pod_list: Dict[str, Any] = json.loads(stdout.decode())
                items: List[Dict[str, Any]] = pod_list.get("items", [])
                return items

            return []

        except Exception as e:
            self.logger.warning(
                "Failed to get controlled pods",
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
                error=str(e),
            )
            return []

    def _verify_resource_requests(
        self,
        manifest: Dict[str, Any],
        original_change: Optional[ResourceChange],
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Verify that resource requests match expected values."""
        if not original_change:
            return True, "No original change data to verify against", {}

        try:
            # Navigate to container resources in the manifest
            containers = (
                manifest.get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("containers", [])
            )

            if not containers:
                return False, "No containers found in resource manifest", {}

            # Check first container (simplified - could be enhanced for multi-container)
            container = containers[0]
            resources = container.get("resources", {})
            resource_requests = resources.get("requests", {})

            # Compare with expected values
            expected_values = original_change.proposed_values
            mismatches = []

            for resource_type, expected_value in expected_values.items():
                actual_value = resource_requests.get(resource_type)
                if actual_value != expected_value:
                    mismatches.append(
                        {
                            "resource_type": resource_type,
                            "expected": expected_value,
                            "actual": actual_value,
                        }
                    )

            if mismatches:
                return (
                    False,
                    f"Resource requests don't match expected values",
                    {
                        "mismatches": mismatches,
                        "expected": expected_values,
                        "actual": resource_requests,
                    },
                )

            return (
                True,
                "Resource requests match expected values",
                {
                    "verified_resources": expected_values,
                },
            )

        except Exception as e:
            return (
                False,
                f"Error verifying resource requests: {str(e)}",
                {
                    "error": str(e),
                },
            )

    def _check_resource_health(
        self,
        manifest: Dict[str, Any],
        resource_type: str,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Check resource-specific health indicators."""
        try:
            status = manifest.get("status", {})

            if resource_type.lower() == "deployment":
                # Check deployment status
                replicas = status.get("replicas", 0)
                ready_replicas = status.get("readyReplicas", 0)
                available_replicas = status.get("availableReplicas", 0)

                is_healthy = (
                    replicas > 0
                    and ready_replicas == replicas
                    and available_replicas == replicas
                )

                message = f"Deployment health: {ready_replicas}/{replicas} replicas ready, {available_replicas} available"

                details = {
                    "replicas": replicas,
                    "ready_replicas": ready_replicas,
                    "available_replicas": available_replicas,
                    "conditions": status.get("conditions", []),
                }

                return is_healthy, message, details

            else:
                # Generic health check for other resource types
                conditions = status.get("conditions", [])
                healthy_conditions = [
                    c
                    for c in conditions
                    if c.get("status") == "True"
                    and c.get("type") in ["Available", "Ready", "Progressing"]
                ]

                is_healthy = len(healthy_conditions) > 0
                message = (
                    f"Resource health: {len(healthy_conditions)} healthy conditions"
                )

                details = {
                    "conditions": conditions,
                    "healthy_conditions": len(healthy_conditions),
                }

                return is_healthy, message, details

        except Exception as e:
            return False, f"Error checking resource health: {str(e)}", {"error": str(e)}

    def _check_pod_readiness(self, pod: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if a pod is ready."""
        try:
            status = pod.get("status", {})
            phase = status.get("phase", "Unknown")

            if phase != "Running":
                return False, f"Pod phase: {phase}"

            # Check readiness conditions
            conditions = status.get("conditions", [])
            ready_condition = None

            for condition in conditions:
                if condition.get("type") == "Ready":
                    ready_condition = condition
                    break

            if not ready_condition:
                return False, "No Ready condition found"

            is_ready = ready_condition.get("status") == "True"
            if not is_ready:
                reason = ready_condition.get("reason", "Unknown")
                return False, f"Not ready: {reason}"

            return True, "Ready"

        except Exception as e:
            return False, f"Error checking readiness: {str(e)}"

    def _check_pod_stability(self, pod: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if a pod is stable (no restart loops, errors, etc.)."""
        try:
            status = pod.get("status", {})

            # Check for excessive restarts
            container_statuses = status.get("containerStatuses", [])
            for container_status in container_statuses:
                restart_count = container_status.get("restartCount", 0)
                if restart_count > 5:  # Configurable threshold
                    return False, f"High restart count: {restart_count}"

                # Check container state
                state = container_status.get("state", {})
                if "waiting" in state:
                    waiting_reason = state["waiting"].get("reason", "Unknown")
                    if waiting_reason in [
                        "CrashLoopBackOff",
                        "ImagePullBackOff",
                        "ErrImagePull",
                    ]:
                        return False, f"Container waiting: {waiting_reason}"

            return True, "Stable"

        except Exception as e:
            return False, f"Error checking stability: {str(e)}"
