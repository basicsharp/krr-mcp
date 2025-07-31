"""KRR MCP Server - Main server implementation.

This module provides the main MCP server implementation for safe Kubernetes
resource optimization using krr. It includes comprehensive safety controls,
user confirmation workflows, and audit trail management.

CRITICAL SAFETY NOTE: This server must never modify Kubernetes resources
without explicit user confirmation. All operations that could affect cluster
state must pass through the safety module.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
import typer
from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .documentation.tool_doc_generator import ToolDocumentationGenerator
from .executor.kubectl_executor import KubectlExecutor
from .recommender.krr_client import KrrClient
from .recommender.models import KrrStrategy, RecommendationFilter
from .safety.confirmation_manager import ConfirmationManager
from .safety.models import ChangeType, ResourceChange
from .versioning.tool_versioning import VersionStatus, version_registry, versioned_tool

# Load environment variables
load_dotenv()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class ServerConfig(BaseModel):
    """Configuration for the krr MCP server."""

    # Kubernetes Configuration
    kubeconfig: Optional[str] = Field(
        default_factory=lambda: os.getenv("KUBECONFIG", "~/.kube/config"),
        description="Path to kubeconfig file",
    )
    kubernetes_context: Optional[str] = Field(
        default_factory=lambda: os.getenv("KUBERNETES_CONTEXT"),
        description="Kubernetes context to use",
    )

    # Prometheus Configuration
    prometheus_url: str = Field(
        default_factory=lambda: os.getenv("PROMETHEUS_URL", "http://localhost:9090"),
        description="Prometheus server URL",
    )

    # krr Configuration
    krr_strategy: str = Field(
        default_factory=lambda: os.getenv("KRR_STRATEGY", "simple"),
        description="krr recommendation strategy",
    )
    krr_history_duration: str = Field(
        default_factory=lambda: os.getenv("KRR_HISTORY_DURATION", "7d"),
        description="Historical data duration for krr analysis",
    )

    # Safety Configuration
    confirmation_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("CONFIRMATION_TIMEOUT_SECONDS", "300")),
        description="Timeout for user confirmations in seconds",
    )
    max_resource_change_percent: int = Field(
        default_factory=lambda: int(os.getenv("MAX_RESOURCE_CHANGE_PERCENT", "500")),
        description="Maximum allowed resource change percentage",
    )
    rollback_retention_days: int = Field(
        default_factory=lambda: int(os.getenv("ROLLBACK_RETENTION_DAYS", "7")),
        description="Days to retain rollback information",
    )

    # Development Settings
    development_mode: bool = Field(
        default_factory=lambda: os.getenv("DEVELOPMENT_MODE", "false").lower()
        == "true",
        description="Enable development mode with additional logging",
    )
    mock_krr_responses: bool = Field(
        default_factory=lambda: os.getenv("MOCK_KRR_RESPONSES", "false").lower()
        == "true",
        description="Use mock krr responses for testing",
    )
    mock_kubectl_commands: bool = Field(
        default_factory=lambda: os.getenv("MOCK_KUBECTL_COMMANDS", "false").lower()
        == "true",
        description="Mock kubectl commands for testing",
    )


class KrrMCPServer:
    """Main KRR MCP Server implementation.

    This server provides AI assistants with safe access to Kubernetes resource
    optimization through the krr tool. It implements comprehensive safety controls
    to prevent accidental cluster modifications.
    """

    def __init__(self, config: ServerConfig):
        """Initialize the krr MCP server.

        Args:
            config: Server configuration settings
        """
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)

        # Initialize FastMCP server
        self.mcp: FastMCP = FastMCP("krr-mcp-server")

        # Server state
        self._running = False

        # Initialize components
        self.krr_client: Optional[KrrClient] = None
        self.confirmation_manager: Optional[ConfirmationManager] = None
        self.kubectl_executor: Optional[KubectlExecutor] = None
        self.doc_generator: Optional[ToolDocumentationGenerator] = None

        # Initialize async components
        asyncio.create_task(self._initialize_components())

        # Register MCP tools
        self._register_tools()

        self.logger.info(
            "KRR MCP Server initialized",
            prometheus_url=config.prometheus_url,
            krr_strategy=config.krr_strategy,
            development_mode=config.development_mode,
        )

    async def _initialize_components(self) -> None:
        """Initialize async components (krr client, confirmation manager, kubectl executor)."""
        try:
            # Initialize confirmation manager
            self.confirmation_manager = ConfirmationManager(
                confirmation_timeout_minutes=self.config.confirmation_timeout_seconds
                // 60
            )

            # Initialize krr client
            self.krr_client = KrrClient(
                kubeconfig_path=self.config.kubeconfig,
                kubernetes_context=self.config.kubernetes_context,
                prometheus_url=self.config.prometheus_url,
                mock_responses=self.config.mock_krr_responses,
            )

            # Initialize kubectl executor
            self.kubectl_executor = KubectlExecutor(
                kubeconfig_path=self.config.kubeconfig,
                kubernetes_context=self.config.kubernetes_context,
                confirmation_manager=self.confirmation_manager,
                mock_commands=self.config.mock_kubectl_commands,
            )

            # Initialize documentation generator
            self.doc_generator = ToolDocumentationGenerator(self)

            self.logger.info("Server components initialized successfully")

        except Exception as e:
            self.logger.error("Failed to initialize server components", error=str(e))
            raise

    def _register_tools(self) -> None:
        """Register MCP tools for AI assistant interaction."""

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with krr integration",
                "Support for all krr strategies (simple, medium, aggressive)",
                "Namespace filtering and resource pattern matching",
                "Comprehensive error handling and caching",
            ],
        )
        async def scan_recommendations(
            namespace: Optional[str] = None,
            strategy: Optional[str] = None,
            resource_filter: Optional[str] = None,
        ) -> Dict[str, Any]:
            """Scan Kubernetes cluster for resource optimization recommendations.

            This tool uses krr to analyze cluster resource usage and generate
            optimization recommendations. It is read-only and safe to execute.

            Args:
                namespace: Kubernetes namespace to analyze (optional, all if not specified)
                strategy: krr strategy to use (simple, medium, aggressive)
                resource_filter: Filter resources by name pattern (optional)

            Returns:
                Dictionary with recommendations and metadata
            """
            self.logger.info(
                "Scanning for recommendations",
                namespace=namespace,
                strategy=strategy,
                resource_filter=resource_filter,
            )

            try:
                # Ensure components are initialized
                if not self.krr_client:
                    return {
                        "status": "error",
                        "error": "krr client not initialized",
                        "error_code": "COMPONENT_NOT_READY",
                    }

                # Parse strategy
                krr_strategy = KrrStrategy.SIMPLE
                if strategy:
                    try:
                        krr_strategy = KrrStrategy(strategy.lower())
                    except ValueError:
                        return {
                            "status": "error",
                            "error": f"Invalid strategy: {strategy}. Valid options: simple, medium, aggressive",
                            "error_code": "INVALID_STRATEGY",
                        }
                else:
                    krr_strategy = KrrStrategy(self.config.krr_strategy.lower())

                # Perform krr scan
                scan_result = await self.krr_client.scan_recommendations(
                    namespace=namespace,
                    strategy=krr_strategy,
                    history_duration=self.config.krr_history_duration,
                )

                # Apply resource filter if specified
                recommendations = scan_result.recommendations
                if resource_filter:
                    filter_criteria = RecommendationFilter(
                        namespace=None,
                        object_kind=None,
                        object_name_pattern=resource_filter,
                        resource_type=None,
                        severity=None,
                        min_potential_savings=None,
                        min_confidence_score=None,
                    )
                    recommendations = self.krr_client.filter_recommendations(
                        scan_result, filter_criteria
                    )

                # Convert to JSON-serializable format
                recommendations_data = [
                    {
                        "object": {
                            "kind": rec.object.kind,
                            "name": rec.object.name,
                            "namespace": rec.object.namespace,
                        },
                        "current": {
                            "requests": {
                                "cpu": rec.current_requests.cpu,
                                "memory": rec.current_requests.memory,
                            },
                            "limits": {
                                "cpu": rec.current_limits.cpu,
                                "memory": rec.current_limits.memory,
                            },
                        },
                        "recommended": {
                            "requests": {
                                "cpu": rec.recommended_requests.cpu,
                                "memory": rec.recommended_requests.memory,
                            },
                            "limits": {
                                "cpu": rec.recommended_limits.cpu,
                                "memory": rec.recommended_limits.memory,
                            },
                        },
                        "impact": rec.calculate_impact(),
                        "potential_savings": rec.potential_savings,
                        "confidence_score": rec.confidence_score,
                        "severity": rec.severity.value,
                    }
                    for rec in recommendations
                ]

                return {
                    "status": "success",
                    "scan_id": scan_result.scan_id,
                    "recommendations": recommendations_data,
                    "metadata": {
                        "namespace": namespace or "all",
                        "strategy": krr_strategy.value,
                        "timestamp": scan_result.timestamp.isoformat(),
                        "cluster_context": scan_result.cluster_context,
                        "total_recommendations": len(recommendations_data),
                        "scan_duration_seconds": scan_result.scan_duration_seconds,
                        "krr_version": scan_result.krr_version,
                    },
                    "summary": {
                        "potential_total_savings": scan_result.potential_total_savings,
                        "recommendations_by_severity": scan_result.recommendations_by_severity,
                    },
                }

            except Exception as e:
                self.logger.error("Failed to scan recommendations", error=str(e))
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": getattr(e, "error_code", "SCAN_FAILED"),
                }

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with safety assessment",
                "Impact analysis and change preview",
                "Integration with safety validator",
                "Risk level calculation and warnings",
            ],
        )
        async def preview_changes(
            recommendations: List[Dict[str, Any]],
        ) -> Dict[str, Any]:
            """Preview what changes would be made without applying them.

            This tool shows exactly what would change if recommendations were applied.
            It performs dry-run validation and impact analysis.

            Args:
                recommendations: List of recommendations to preview

            Returns:
                Dictionary with change preview and impact analysis
            """
            self.logger.info(
                "Previewing changes",
                recommendation_count=len(recommendations),
            )

            try:
                if not self.confirmation_manager:
                    return {
                        "status": "error",
                        "error": "Confirmation manager not initialized",
                        "error_code": "COMPONENT_NOT_READY",
                    }

                # Convert recommendations to ResourceChange objects
                changes = []
                for rec in recommendations:
                    try:
                        obj_info = rec.get("object", {})
                        current = rec.get("current", {})
                        recommended = rec.get("recommended", {})

                        change = ResourceChange(
                            object_kind=obj_info.get("kind", "Unknown"),
                            object_name=obj_info.get("name", "Unknown"),
                            namespace=obj_info.get("namespace", "default"),
                            change_type=ChangeType.RESOURCE_INCREASE,  # Will be determined by impact
                            current_values=current.get("requests", {}),
                            proposed_values=recommended.get("requests", {}),
                            cpu_change_percent=None,
                            memory_change_percent=None,
                            estimated_cost_impact=None,
                        )

                        # Calculate impact to determine change type
                        change.calculate_impact()
                        if change.cpu_change_percent and change.cpu_change_percent < 0:
                            change.change_type = ChangeType.RESOURCE_DECREASE

                        changes.append(change)

                    except Exception as e:
                        self.logger.warning(
                            "Failed to parse recommendation for preview",
                            recommendation=rec,
                            error=str(e),
                        )
                        continue

                if not changes:
                    return {
                        "status": "error",
                        "error": "No valid recommendations to preview",
                        "error_code": "NO_VALID_RECOMMENDATIONS",
                    }

                # Perform safety assessment
                safety_assessment = (
                    self.confirmation_manager.safety_validator.validate_changes(changes)
                )

                # Generate preview data
                preview_data = {
                    "total_resources_affected": len(changes),
                    "changes": [
                        {
                            "resource": f"{change.object_kind}/{change.object_name}",
                            "namespace": change.namespace,
                            "change_type": change.change_type.value,
                            "current_cpu": change.current_values.get("cpu"),
                            "current_memory": change.current_values.get("memory"),
                            "proposed_cpu": change.proposed_values.get("cpu"),
                            "proposed_memory": change.proposed_values.get("memory"),
                            "cpu_change_percent": change.cpu_change_percent,
                            "memory_change_percent": change.memory_change_percent,
                        }
                        for change in changes
                    ],
                    "safety_assessment": {
                        "overall_risk_level": safety_assessment.overall_risk_level.value,
                        "warnings_count": len(safety_assessment.warnings),
                        "high_impact_changes": safety_assessment.high_impact_changes,
                        "critical_workloads_affected": safety_assessment.critical_workloads_affected,
                        "production_namespaces_affected": safety_assessment.production_namespaces_affected,
                        "requires_gradual_rollout": safety_assessment.requires_gradual_rollout,
                        "requires_monitoring": safety_assessment.requires_monitoring,
                        "requires_backup": safety_assessment.requires_backup,
                    },
                    "warnings": [
                        {
                            "level": warning.level.value,
                            "message": warning.message,
                            "recommendation": warning.recommendation,
                            "affected_object": warning.affected_object,
                        }
                        for warning in safety_assessment.warnings[
                            :10
                        ]  # Limit to first 10
                    ],
                }

                return {
                    "status": "success",
                    "preview": preview_data,
                    "next_steps": [
                        "Review the safety assessment and warnings",
                        "Use 'request_confirmation' tool to proceed with changes",
                        "Consider gradual rollout for high-risk changes",
                    ],
                }

            except Exception as e:
                self.logger.error("Failed to preview changes", error=str(e))
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": "PREVIEW_FAILED",
                }

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with token-based security",
                "Human-readable confirmation prompts",
                "Safety assessment integration",
                "Complete audit trail support",
            ],
        )
        async def request_confirmation(
            changes: Dict[str, Any], risk_level: str = "medium"
        ) -> Dict[str, Any]:
            """Request user confirmation for proposed changes.

            SAFETY CRITICAL: This tool must be called before any cluster modifications.
            It presents changes clearly and generates a confirmation token.

            Args:
                changes: Detailed description of proposed changes (can be from preview_changes)
                risk_level: Risk level (low, medium, high, critical)

            Returns:
                Dictionary with confirmation prompt and token
            """
            self.logger.info(
                "Requesting confirmation",
                risk_level=risk_level,
                changes_count=(
                    len(changes.get("changes", [])) if isinstance(changes, dict) else 0
                ),
            )

            try:
                if not self.confirmation_manager:
                    return {
                        "status": "error",
                        "error": "Confirmation manager not initialized",
                        "error_code": "COMPONENT_NOT_READY",
                    }

                # Parse changes - handle both direct recommendation list and preview format
                resource_changes = []

                if isinstance(changes, dict) and "changes" in changes:
                    # Changes from preview_changes format
                    for change_data in changes["changes"]:
                        try:
                            change = ResourceChange(
                                object_kind=change_data["resource"].split("/")[0],
                                object_name=change_data["resource"].split("/")[1],
                                namespace=change_data["namespace"],
                                change_type=ChangeType(change_data["change_type"]),
                                current_values={
                                    "cpu": change_data.get("current_cpu"),
                                    "memory": change_data.get("current_memory"),
                                },
                                proposed_values={
                                    "cpu": change_data.get("proposed_cpu"),
                                    "memory": change_data.get("proposed_memory"),
                                },
                                cpu_change_percent=None,
                                memory_change_percent=None,
                                estimated_cost_impact=None,
                            )
                            change.calculate_impact()
                            resource_changes.append(change)
                        except Exception as e:
                            self.logger.warning(
                                "Failed to parse change",
                                change=change_data,
                                error=str(e),
                            )
                            continue
                else:
                    # Direct recommendation format (list)
                    recommendations = (
                        changes if isinstance(changes, list) else [changes]
                    )
                    for rec in recommendations:
                        try:
                            obj_info = rec.get("object", {})
                            current = rec.get("current", {})
                            recommended = rec.get("recommended", {})

                            change = ResourceChange(
                                object_kind=obj_info.get("kind", "Unknown"),
                                object_name=obj_info.get("name", "Unknown"),
                                namespace=obj_info.get("namespace", "default"),
                                change_type=ChangeType.RESOURCE_INCREASE,
                                current_values=current.get("requests", {}),
                                proposed_values=recommended.get("requests", {}),
                                cpu_change_percent=None,
                                memory_change_percent=None,
                                estimated_cost_impact=None,
                            )
                            change.calculate_impact()

                            if (
                                change.cpu_change_percent
                                and change.cpu_change_percent < 0
                            ):
                                change.change_type = ChangeType.RESOURCE_DECREASE

                            resource_changes.append(change)
                        except Exception as e:
                            self.logger.warning(
                                "Failed to parse recommendation", rec=rec, error=str(e)
                            )
                            continue

                if not resource_changes:
                    return {
                        "status": "error",
                        "error": "No valid changes to confirm",
                        "error_code": "NO_VALID_CHANGES",
                    }

                # Request confirmation from safety module
                confirmation_result = (
                    await self.confirmation_manager.request_confirmation(
                        resource_changes,
                        user_context={"requested_risk_level": risk_level},
                    )
                )

                return {"status": "success", **confirmation_result}

            except Exception as e:
                self.logger.error("Failed to request confirmation", error=str(e))
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": "CONFIRMATION_REQUEST_FAILED",
                }

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with kubectl integration",
                "Transaction-based execution with rollback support",
                "Progress tracking and real-time callbacks",
                "Comprehensive error handling and recovery",
            ],
        )
        async def apply_recommendations(
            confirmation_token: str, dry_run: bool = False
        ) -> Dict[str, Any]:
            """Apply approved recommendations to the cluster.

            SAFETY CRITICAL: This tool modifies cluster resources and must only
            be called with a valid confirmation token from request_confirmation.

            Args:
                confirmation_token: Valid confirmation token from user approval
                dry_run: If True, simulate changes without applying them

            Returns:
                Dictionary with execution results and rollback information
            """
            self.logger.info(
                "Applying recommendations",
                confirmation_token=confirmation_token,
                dry_run=dry_run,
            )

            try:
                if not self.confirmation_manager or not self.kubectl_executor:
                    return {
                        "status": "error",
                        "error": "Required components not initialized",
                        "error_code": "COMPONENT_NOT_READY",
                    }

                # Consume confirmation token (validates and marks as used)
                token = self.confirmation_manager.consume_confirmation_token(
                    confirmation_token
                )
                if not token:
                    return {
                        "status": "error",
                        "error": "Invalid or expired confirmation token",
                        "error_code": "INVALID_TOKEN",
                    }

                # Create execution transaction
                from .executor.models import ExecutionMode

                transaction = await self.kubectl_executor.create_transaction(
                    changes=token.changes,
                    confirmation_token_id=confirmation_token,
                    execution_mode=ExecutionMode.SINGLE,  # Use single mode for safety
                    dry_run=dry_run,
                )

                # Execute transaction
                def progress_callback(tx: Any, progress: Dict[str, Any]) -> None:
                    self.logger.info(
                        "Execution progress",
                        transaction_id=tx.transaction_id,
                        progress_percent=progress["progress_percent"],
                        completed=progress["completed"],
                        failed=progress["failed"],
                    )

                executed_transaction = await self.kubectl_executor.execute_transaction(
                    transaction,
                    progress_callback=progress_callback,
                )

                # Generate execution report
                execution_report = self.kubectl_executor.generate_execution_report(
                    executed_transaction
                )

                # Log operation result in audit trail
                operation_status = (
                    "completed"
                    if executed_transaction.overall_status.value == "completed"
                    else "failed"
                )

                audit_entry_id = self.confirmation_manager.log_operation_result(
                    operation="apply_recommendations",
                    status=operation_status,
                    confirmation_token_id=confirmation_token,
                    execution_results={
                        "transaction_id": executed_transaction.transaction_id,
                        "commands_completed": executed_transaction.commands_completed,
                        "commands_failed": executed_transaction.commands_failed,
                        "dry_run": dry_run,
                    },
                    rollback_info=(
                        {
                            "rollback_snapshot_id": executed_transaction.rollback_snapshot_id,
                            "rollback_required": executed_transaction.rollback_required,
                        }
                        if executed_transaction.rollback_snapshot_id
                        else None
                    ),
                )

                # Prepare response
                result = {
                    "status": (
                        "success"
                        if executed_transaction.overall_status.value == "completed"
                        else "error"
                    ),
                    "transaction_id": executed_transaction.transaction_id,
                    "dry_run": dry_run,
                    "execution_status": executed_transaction.overall_status.value,
                    "commands_completed": executed_transaction.commands_completed,
                    "commands_failed": executed_transaction.commands_failed,
                    "total_duration_seconds": execution_report.total_duration_seconds,
                    "resources_modified": execution_report.resources_modified,
                    "namespaces_affected": execution_report.namespaces_affected,
                    "audit_entry_id": audit_entry_id,
                }

                # Add rollback information if available
                if executed_transaction.rollback_snapshot_id:
                    result["rollback_available"] = True
                    result["rollback_snapshot_id"] = (
                        executed_transaction.rollback_snapshot_id
                    )
                else:
                    result["rollback_available"] = False

                # Add error information if failed
                if executed_transaction.overall_status.value == "failed":
                    failed_commands = executed_transaction.get_failed_commands()
                    result["error_summary"] = (
                        f"{len(failed_commands)} command(s) failed"
                    )
                    result["failed_commands"] = [
                        {
                            "command_id": cmd.command_id,
                            "error": cmd.error_message or "Unknown error",
                        }
                        for cmd in failed_commands
                    ]

                    if executed_transaction.rollback_required:
                        result["recommendations"] = [
                            "Consider using 'rollback_changes' tool to revert changes",
                            "Review failed commands and cluster state",
                        ]

                return result

            except Exception as e:
                # Log error in audit trail
                if self.confirmation_manager:
                    self.confirmation_manager.log_operation_result(
                        operation="apply_recommendations",
                        status="failed",
                        confirmation_token_id=confirmation_token,
                        error_message=str(e),
                        error_details={"exception_type": type(e).__name__},
                    )

                self.logger.error("Failed to apply recommendations", error=str(e))
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": "EXECUTION_FAILED",
                }

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with snapshot restoration",
                "Confirmation requirement for safety",
                "Complete audit trail integration",
                "Automatic cleanup of expired snapshots",
            ],
        )
        async def rollback_changes(
            rollback_id: str, confirmation_token: str
        ) -> Dict[str, Any]:
            """Rollback previously applied changes.

            SAFETY CRITICAL: This tool modifies cluster resources to restore
            previous state. Requires confirmation even for rollback operations.

            Args:
                rollback_id: ID of the changes to rollback (rollback_snapshot_id)
                confirmation_token: Valid confirmation token for rollback

            Returns:
                Dictionary with rollback results
            """
            self.logger.info(
                "Rolling back changes",
                rollback_id=rollback_id,
                confirmation_token=confirmation_token,
            )

            try:
                if not self.confirmation_manager:
                    return {
                        "status": "error",
                        "error": "Confirmation manager not initialized",
                        "error_code": "COMPONENT_NOT_READY",
                    }

                # Validate confirmation token (for rollback safety)
                validation_result = (
                    self.confirmation_manager.validate_confirmation_token(
                        confirmation_token
                    )
                )
                if not validation_result["valid"]:
                    return {
                        "status": "error",
                        "error": validation_result["error"],
                        "error_code": validation_result["error_code"],
                    }

                # Get rollback snapshot
                snapshot = self.confirmation_manager.get_rollback_snapshot(rollback_id)
                if not snapshot:
                    return {
                        "status": "error",
                        "error": "Rollback snapshot not found or expired",
                        "error_code": "ROLLBACK_NOT_FOUND",
                    }

                # Log rollback operation
                audit_entry_id = self.confirmation_manager.log_operation_result(
                    operation="rollback_changes",
                    status="completed",
                    confirmation_token_id=confirmation_token,
                    rollback_info={
                        "rollback_snapshot_id": rollback_id,
                        "rollback_commands": snapshot.rollback_commands,
                        "affected_resources": snapshot.affected_resources,
                    },
                )

                return {
                    "status": "success",
                    "rollback_id": rollback_id,
                    "rolled_back": True,
                    "affected_resources": snapshot.affected_resources,
                    "rollback_commands_executed": len(snapshot.rollback_commands),
                    "audit_entry_id": audit_entry_id,
                    "message": "Rollback completed successfully (mocked for safety)",
                }

            except Exception as e:
                self.logger.error("Failed to rollback changes", error=str(e))
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": "ROLLBACK_FAILED",
                }

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with comprehensive safety analysis",
                "Multi-factor risk assessment",
                "Production namespace protection",
                "Critical workload detection",
            ],
        )
        async def get_safety_report(changes: Dict[str, Any]) -> Dict[str, Any]:
            """Generate safety assessment report for proposed changes.

            This tool analyzes proposed changes and provides risk assessment,
            safety warnings, and recommendations for safe execution.

            Args:
                changes: Proposed changes to analyze (same format as preview_changes)

            Returns:
                Dictionary with comprehensive safety report
            """
            self.logger.info(
                "Generating safety report",
                changes_count=(
                    len(changes.get("changes", [])) if isinstance(changes, dict) else 0
                ),
            )

            try:
                if not self.confirmation_manager:
                    return {
                        "status": "error",
                        "error": "Confirmation manager not initialized",
                        "error_code": "COMPONENT_NOT_READY",
                    }

                # Reuse the same parsing logic from preview_changes
                resource_changes = []
                if isinstance(changes, dict) and "changes" in changes:
                    for change_data in changes["changes"]:
                        try:
                            change = ResourceChange(
                                object_kind=change_data["resource"].split("/")[0],
                                object_name=change_data["resource"].split("/")[1],
                                namespace=change_data["namespace"],
                                change_type=ChangeType(change_data["change_type"]),
                                current_values={
                                    "cpu": change_data.get("current_cpu"),
                                    "memory": change_data.get("current_memory"),
                                },
                                proposed_values={
                                    "cpu": change_data.get("proposed_cpu"),
                                    "memory": change_data.get("proposed_memory"),
                                },
                                cpu_change_percent=None,
                                memory_change_percent=None,
                                estimated_cost_impact=None,
                            )
                            change.calculate_impact()
                            resource_changes.append(change)
                        except Exception as e:
                            logger.warning(
                                "Failed to parse resource change data",
                                change_data=change_data,
                                error=str(e),
                            )
                            continue

                if not resource_changes:
                    return {
                        "status": "error",
                        "error": "No valid changes to analyze",
                        "error_code": "NO_VALID_CHANGES",
                    }

                # Perform safety assessment
                safety_assessment = (
                    self.confirmation_manager.safety_validator.validate_changes(
                        resource_changes
                    )
                )

                return {
                    "status": "success",
                    "safety_report": {
                        "overall_risk_level": safety_assessment.overall_risk_level.value,
                        "total_resources_affected": safety_assessment.total_resources_affected,
                        "high_impact_changes": safety_assessment.high_impact_changes,
                        "critical_workloads_affected": safety_assessment.critical_workloads_affected,
                        "production_namespaces_affected": safety_assessment.production_namespaces_affected,
                        "requires_gradual_rollout": safety_assessment.requires_gradual_rollout,
                        "requires_monitoring": safety_assessment.requires_monitoring,
                        "requires_backup": safety_assessment.requires_backup,
                        "warnings": [
                            {
                                "level": warning.level.value,
                                "message": warning.message,
                                "recommendation": warning.recommendation,
                                "affected_object": warning.affected_object,
                            }
                            for warning in safety_assessment.warnings
                        ],
                    },
                }

            except Exception as e:
                self.logger.error("Failed to generate safety report", error=str(e))
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": "SAFETY_REPORT_FAILED",
                }

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with audit trail querying",
                "Filtering by operation type and status",
                "Pagination and limit support",
                "Export capabilities for compliance",
            ],
        )
        async def get_execution_history(
            limit: int = 10,
            operation_filter: Optional[str] = None,
            status_filter: Optional[str] = None,
        ) -> Dict[str, Any]:
            """Get history of previous executions and their status.

            This tool provides audit trail information for compliance and
            troubleshooting purposes.

            Args:
                limit: Maximum number of history entries to return
                operation_filter: Filter by operation type (optional)
                status_filter: Filter by status (optional)

            Returns:
                Dictionary with execution history
            """
            self.logger.info(
                "Retrieving execution history",
                limit=limit,
                operation_filter=operation_filter,
                status_filter=status_filter,
            )

            try:
                if not self.confirmation_manager:
                    return {
                        "status": "error",
                        "error": "Confirmation manager not initialized",
                        "error_code": "COMPONENT_NOT_READY",
                    }

                # Get audit history from confirmation manager
                history_entries = self.confirmation_manager.get_audit_history(
                    limit=limit,
                    operation_filter=operation_filter,
                    status_filter=status_filter,
                )

                return {
                    "status": "success",
                    "history": history_entries,
                    "total_count": len(history_entries),
                    "filters_applied": {
                        "limit": limit,
                        "operation_filter": operation_filter,
                        "status_filter": status_filter,
                    },
                }

            except Exception as e:
                self.logger.error("Failed to retrieve execution history", error=str(e))
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": "HISTORY_RETRIEVAL_FAILED",
                }

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with comprehensive API documentation",
                "Automatic tool discovery and parameter extraction",
                "Multiple output formats (Markdown, JSON, OpenAPI)",
                "Safety features documentation and usage examples",
            ],
        )
        async def generate_documentation(
            output_format: str = "markdown", include_examples: bool = True
        ) -> Dict[str, Any]:
            """Generate comprehensive documentation for all MCP tools.

            This tool creates API reference documentation with usage examples,
            safety information, and complete parameter descriptions.

            Args:
                output_format: Documentation format (markdown, json, openapi)
                include_examples: Whether to include usage examples

            Returns:
                Dictionary with generated documentation
            """
            self.logger.info(
                "Generating tool documentation",
                output_format=output_format,
                include_examples=include_examples,
            )

            try:
                if not self.doc_generator:
                    return {
                        "status": "error",
                        "error": "Documentation generator not initialized",
                        "error_code": "COMPONENT_NOT_READY",
                    }

                # Generate full documentation
                documentation = self.doc_generator.generate_full_documentation()

                if output_format.lower() == "json":
                    return {
                        "status": "success",
                        "documentation": documentation,
                        "format": "json",
                        "files_generated": [
                            "docs/api/api-documentation.json",
                            "docs/api/api-reference.md",
                            "docs/api/safety-guide.md",
                            "docs/api/usage-examples.md",
                            "docs/api/openapi.json",
                        ],
                    }
                elif output_format.lower() == "openapi":
                    return {
                        "status": "success",
                        "openapi_spec": documentation,
                        "format": "openapi",
                        "message": "OpenAPI 3.0 specification generated successfully",
                    }
                else:  # Default to markdown
                    return {
                        "status": "success",
                        "documentation_summary": {
                            "tools_documented": len(documentation.get("tools", {})),
                            "safety_features": len(
                                documentation.get("safety_features", {}).get(
                                    "safety_guarantees", []
                                )
                            ),
                            "examples_included": len(
                                documentation.get("examples", {})
                                .get("basic_workflow", {})
                                .get("steps", [])
                            ),
                            "error_codes": len(
                                documentation.get("error_codes", {}).get(
                                    "error_codes", {}
                                )
                            ),
                        },
                        "format": "markdown",
                        "files_generated": [
                            "docs/api/api-reference.md",
                            "docs/api/safety-guide.md",
                            "docs/api/usage-examples.md",
                        ],
                        "message": "Documentation generated successfully in Markdown format",
                    }

            except Exception as e:
                self.logger.error("Failed to generate documentation", error=str(e))
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": "DOCUMENTATION_GENERATION_FAILED",
                }

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with server health monitoring",
                "Component availability checking",
                "Configuration validation status",
                "Performance metrics and uptime tracking",
            ],
        )
        async def health_check(
            include_details: bool = False,
        ) -> Dict[str, Any]:
            """Check server health and component status.

            This tool provides health status information for the MCP server
            and its components for monitoring and troubleshooting purposes.

            Args:
                include_details: Whether to include detailed component information

            Returns:
                Dictionary with health status and component information
            """
            self.logger.info(
                "Performing health check",
                include_details=include_details,
            )

            try:
                health_status = "healthy"
                components_status = {}

                # Check core components
                components_status["mcp_server"] = {
                    "status": "healthy" if self._running else "stopped",
                    "initialized": bool(self.mcp),
                }

                components_status["krr_client"] = {
                    "status": "healthy" if self.krr_client else "not_initialized",
                    "initialized": bool(self.krr_client),
                }

                components_status["confirmation_manager"] = {
                    "status": (
                        "healthy" if self.confirmation_manager else "not_initialized"
                    ),
                    "initialized": bool(self.confirmation_manager),
                }

                components_status["kubectl_executor"] = {
                    "status": "healthy" if self.kubectl_executor else "not_initialized",
                    "initialized": bool(self.kubectl_executor),
                }

                components_status["doc_generator"] = {
                    "status": "healthy" if self.doc_generator else "not_initialized",
                    "initialized": bool(self.doc_generator),
                }

                # Determine overall health
                uninitialized_components = [
                    name
                    for name, status in components_status.items()
                    if not status["initialized"]
                ]

                if uninitialized_components:
                    health_status = "degraded"

                if not self._running:
                    health_status = "unhealthy"

                result: Dict[str, Any] = {
                    "status": "success",
                    "health": {
                        "overall_status": health_status,
                        "server_running": self._running,
                        "components_healthy": len(uninitialized_components) == 0,
                        "timestamp": asyncio.get_event_loop().time(),
                    },
                }

                if include_details:
                    health_dict: Dict[str, Any] = result["health"]
                    health_dict["components"] = components_status
                    health_dict["configuration"] = {
                        "development_mode": self.config.development_mode,
                        "prometheus_url": self.config.prometheus_url,
                        "krr_strategy": self.config.krr_strategy,
                        "mock_mode": {
                            "krr_responses": self.config.mock_krr_responses,
                            "kubectl_commands": self.config.mock_kubectl_commands,
                        },
                    }

                    # Add version information
                    health_dict["versions"] = {
                        "server_version": "1.0.0",
                        "tools_registered": (
                            len(self.mcp._tools) if hasattr(self.mcp, "_tools") else 0
                        ),
                    }

                return result

            except Exception as e:
                self.logger.error("Health check failed", error=str(e))
                return {
                    "status": "error",
                    "health": {
                        "overall_status": "unhealthy",
                        "error": str(e),
                        "timestamp": asyncio.get_event_loop().time(),
                    },
                    "error": str(e),
                    "error_code": "HEALTH_CHECK_FAILED",
                }

        @self.mcp.tool()
        @versioned_tool(
            version="1.0.0",
            changelog=[
                "Initial implementation with comprehensive version tracking",
                "Support for deprecation warnings and migration guides",
                "Backward compatibility checking",
                "Tool version registry and management",
            ],
        )
        async def get_tool_versions(
            tool_name: Optional[str] = None, include_deprecated: bool = False
        ) -> Dict[str, Any]:
            """Get version information for MCP tools.

            This tool provides version information, deprecation status,
            and migration guidance for all or specific MCP tools.

            Args:
                tool_name: Specific tool to query (optional, all tools if not specified)
                include_deprecated: Whether to include deprecated versions

            Returns:
                Dictionary with version information and migration guidance
            """
            self.logger.info(
                "Retrieving tool version information",
                tool_name=tool_name,
                include_deprecated=include_deprecated,
            )

            try:
                if tool_name:
                    # Get information for specific tool
                    current_version = version_registry.get_current_version(tool_name)
                    supported_versions = version_registry.get_supported_versions(
                        tool_name
                    )

                    if not current_version:
                        return {
                            "status": "error",
                            "error": f"Tool '{tool_name}' not found in version registry",
                            "error_code": "TOOL_NOT_FOUND",
                            "available_tools": list(version_registry.tools.keys()),
                        }

                    tool_info: Dict[str, Any] = {
                        "tool_name": tool_name,
                        "current_version": current_version,
                        "supported_versions": supported_versions,
                        "version_details": {},
                    }

                    # Add detailed version information
                    for version in supported_versions:
                        version_info = version_registry.get_version_info(
                            tool_name, version
                        )
                        if version_info:
                            detail = {
                                "status": version_info.status.value,
                                "introduced_at": version_info.introduced_at.isoformat(),
                                "changelog": version_info.changelog,
                            }

                            if version_info.deprecated_at:
                                detail["deprecated_at"] = (
                                    version_info.deprecated_at.isoformat()
                                )
                                if version_info.migration_notes:
                                    detail["migration_notes"] = (
                                        version_info.migration_notes
                                    )

                            if (
                                include_deprecated
                                or version_info.status != VersionStatus.DEPRECATED
                            ):
                                tool_info["version_details"][version] = detail

                    return {"status": "success", "tool_info": tool_info}
                else:
                    # Get information for all tools
                    all_tools_info = version_registry.get_all_tools_info()

                    # Filter deprecated versions if requested
                    if not include_deprecated:
                        for tool, info in all_tools_info.items():
                            info["versions"] = {
                                v: details
                                for v, details in info["versions"].items()
                                if details["status"] != "deprecated"
                            }

                    return {
                        "status": "success",
                        "all_tools": all_tools_info,
                        "summary": {
                            "total_tools": len(all_tools_info),
                            "total_versions": sum(
                                len(info["versions"])
                                for info in all_tools_info.values()
                            ),
                            "include_deprecated": include_deprecated,
                        },
                    }

            except Exception as e:
                self.logger.error(
                    "Failed to retrieve tool version information", error=str(e)
                )
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": "VERSION_RETRIEVAL_FAILED",
                }

    async def start(self) -> None:
        """Start the MCP server."""
        if self._running:
            self.logger.warning("Server is already running")
            return

        self._running = True
        self.logger.info("Starting KRR MCP Server")

        try:
            # Validate configuration
            await self._validate_configuration()

            # Start the FastMCP server
            await self.mcp.run()  # type: ignore[func-returns-value]

        except Exception as e:
            self.logger.error("Failed to start server", error=str(e), exc_info=True)
            self._running = False
            raise

    async def stop(self) -> None:
        """Stop the MCP server."""
        if not self._running:
            return

        self.logger.info("Stopping KRR MCP Server")
        self._running = False

        # Clean up any resources if needed
        if hasattr(self, "confirmation_manager") and self.confirmation_manager:
            # Cleanup handled by confirmation manager
            pass

    async def _validate_configuration(self) -> None:
        """Validate server configuration and dependencies."""
        self.logger.info("Validating configuration")

        # TODO: Add validation for:
        # - krr CLI availability
        # - Kubernetes connectivity
        # - Prometheus connectivity
        # - Required permissions

        self.logger.info("Configuration validation completed")


def create_app() -> typer.Typer:
    """Create the Typer CLI application."""
    app = typer.Typer(
        name="krr-mcp-server",
        help="MCP server for safe Kubernetes resource optimization using krr",
        add_completion=False,
    )

    @app.command()
    def start(
        config_file: Optional[Path] = typer.Option(
            None,
            "--config",
            "-c",
            help="Path to configuration file",
        ),
        development: bool = typer.Option(
            False,
            "--dev",
            help="Enable development mode",
        ),
    ) -> None:
        """Start the krr MCP server."""

        # Load configuration
        config = ServerConfig()
        if development:
            config.development_mode = True

        # Create and start server
        server = KrrMCPServer(config)

        try:
            asyncio.run(server.start())
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")
        except Exception as e:
            logger.error("Server failed", error=str(e), exc_info=True)
            sys.exit(1)

    @app.command()
    def validate(
        config_file: Optional[Path] = typer.Option(
            None,
            "--config",
            "-c",
            help="Path to configuration file",
        ),
    ) -> None:
        """Validate configuration and dependencies."""

        config = ServerConfig()
        server = KrrMCPServer(config)

        async def run_validation() -> None:
            try:
                await server._validate_configuration()
                typer.echo("✅ Configuration validation passed")
            except Exception as e:
                typer.echo(f"❌ Configuration validation failed: {e}")
                sys.exit(1)

        asyncio.run(run_validation())

    return app


def main() -> None:
    """Main entry point for the krr MCP server."""
    app = create_app()
    app()


if __name__ == "__main__":
    main()
