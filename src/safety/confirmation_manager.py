"""Confirmation management for KRR MCP Server.

This module handles user confirmation workflows, token management,
and audit trail for all safety-critical operations.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from .models import (
    AuditLogEntry,
    ConfirmationToken,
    ResourceChange,
    RollbackSnapshot,
    SafetyAssessment,
)
from .validator import SafetyValidator

logger = structlog.get_logger(__name__)


class ConfirmationManager:
    """Manages confirmation workflows and audit trails."""

    def __init__(self, confirmation_timeout_minutes: int = 5):
        """Initialize the confirmation manager.

        Args:
            confirmation_timeout_minutes: Default timeout for confirmations
        """
        self.confirmation_timeout_minutes = confirmation_timeout_minutes
        self.safety_validator = SafetyValidator()
        self.logger = structlog.get_logger(self.__class__.__name__)

        # In-memory storage (in production, this should be persistent)
        self._confirmation_tokens: Dict[str, ConfirmationToken] = {}
        self._audit_log: List[AuditLogEntry] = []
        self._rollback_snapshots: Dict[str, RollbackSnapshot] = {}

    async def request_confirmation(
        self,
        changes: List[ResourceChange],
        user_context: Optional[Dict[str, Any]] = None,
        custom_timeout_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Request user confirmation for proposed changes.

        Args:
            changes: List of resource changes requiring confirmation
            user_context: Additional user context information
            custom_timeout_minutes: Custom timeout override

        Returns:
            Dictionary containing confirmation prompt and token information
        """
        self.logger.info(
            "Processing confirmation request",
            change_count=len(changes),
            user_context=user_context or {},
        )

        # Validate changes and assess safety
        safety_assessment = self.safety_validator.validate_changes(changes)

        # Create confirmation token
        timeout_minutes = custom_timeout_minutes or self.confirmation_timeout_minutes
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)

        token = ConfirmationToken(
            expires_at=expires_at,
            changes=changes,
            safety_assessment=safety_assessment,
            used=False,
            used_at=None,
            user_context=user_context or {},
        )

        # Store token
        self._confirmation_tokens[token.token_id] = token

        # Create audit log entry
        audit_entry = AuditLogEntry(
            operation="confirmation_requested",
            status="requested",
            user_context=user_context or {},
            changes=changes,
            confirmation_token_id=token.token_id,
            safety_assessment=safety_assessment,
            rollback_info=None,
            error_message=None,
            error_details=None,
        )
        self._audit_log.append(audit_entry)

        # Generate confirmation prompt
        prompt = self._generate_confirmation_prompt(changes, safety_assessment)

        self.logger.info(
            "Confirmation request created",
            token_id=token.token_id,
            risk_level=safety_assessment.overall_risk_level.value,
            expires_at=expires_at.isoformat(),
        )

        return {
            "confirmation_required": True,
            "confirmation_token": token.token_id,
            "expires_at": expires_at.isoformat(),
            "timeout_minutes": timeout_minutes,
            "safety_assessment": safety_assessment.model_dump(),
            "confirmation_prompt": prompt,
            "changes_summary": self._generate_changes_summary(changes),
        }

    def validate_confirmation_token(self, token_id: str) -> Dict[str, Any]:
        """Validate a confirmation token.

        Args:
            token_id: The confirmation token ID to validate

        Returns:
            Dictionary with validation results
        """
        self.logger.info("Validating confirmation token", token_id=token_id)

        # Check if token exists
        if token_id not in self._confirmation_tokens:
            self.logger.warning("Token not found", token_id=token_id)
            return {
                "valid": False,
                "error": "Token not found",
                "error_code": "TOKEN_NOT_FOUND",
            }

        token = self._confirmation_tokens[token_id]

        # Check if token has already been used
        if token.used:
            self.logger.warning(
                "Token already used", token_id=token_id, used_at=token.used_at
            )
            return {
                "valid": False,
                "error": "Token has already been used",
                "error_code": "TOKEN_ALREADY_USED",
                "used_at": token.used_at.isoformat() if token.used_at else None,
            }

        # Check if token has expired
        if token.is_expired():
            self.logger.warning(
                "Token expired", token_id=token_id, expires_at=token.expires_at
            )
            return {
                "valid": False,
                "error": "Token has expired",
                "error_code": "TOKEN_EXPIRED",
                "expires_at": token.expires_at.isoformat(),
            }

        self.logger.info("Token validation successful", token_id=token_id)
        return {
            "valid": True,
            "token": token.model_dump(),
            "changes": [change.model_dump() for change in token.changes],
            "safety_assessment": token.safety_assessment.model_dump(),
        }

    def consume_confirmation_token(self, token_id: str) -> Optional[ConfirmationToken]:
        """Consume a confirmation token (mark as used).

        Args:
            token_id: The confirmation token ID to consume

        Returns:
            The consumed token if valid, None otherwise
        """
        validation_result = self.validate_confirmation_token(token_id)

        if not validation_result["valid"]:
            self.logger.error(
                "Cannot consume invalid token",
                token_id=token_id,
                error=validation_result["error"],
            )
            return None

        token = self._confirmation_tokens[token_id]
        token.mark_used()

        # Create audit log entry
        audit_entry = AuditLogEntry(
            operation="confirmation_consumed",
            status="approved",
            confirmation_token_id=token_id,
            changes=token.changes,
            safety_assessment=token.safety_assessment,
            user_context=token.user_context,
            rollback_info=None,
            error_message=None,
            error_details=None,
        )
        self._audit_log.append(audit_entry)

        self.logger.info("Token consumed successfully", token_id=token_id)
        return token

    def create_rollback_snapshot(
        self,
        operation_id: str,
        confirmation_token_id: str,
        original_manifests: List[Dict[str, Any]],
        rollback_commands: List[str],
        cluster_context: Dict[str, str],
        retention_days: int = 7,
    ) -> str:
        """Create a rollback snapshot.

        Args:
            operation_id: Unique ID for the operation
            confirmation_token_id: Associated confirmation token ID
            original_manifests: Original Kubernetes manifests
            rollback_commands: Commands to execute rollback
            cluster_context: Cluster context information
            retention_days: Days to retain the snapshot

        Returns:
            Snapshot ID
        """
        expires_at = datetime.now(timezone.utc) + timedelta(days=retention_days)

        snapshot = RollbackSnapshot(
            operation_id=operation_id,
            confirmation_token_id=confirmation_token_id,
            original_manifests=original_manifests,
            rollback_commands=rollback_commands,
            cluster_context=cluster_context,
            affected_resources=[],  # Will be populated from original_manifests by validator
            expires_at=expires_at,
        )

        self._rollback_snapshots[snapshot.snapshot_id] = snapshot

        self.logger.info(
            "Rollback snapshot created",
            snapshot_id=snapshot.snapshot_id,
            operation_id=operation_id,
            expires_at=expires_at.isoformat(),
        )

        return snapshot.snapshot_id

    def get_rollback_snapshot(self, snapshot_id: str) -> Optional[RollbackSnapshot]:
        """Get a rollback snapshot by ID.

        Args:
            snapshot_id: The snapshot ID

        Returns:
            RollbackSnapshot if found and not expired, None otherwise
        """
        if snapshot_id not in self._rollback_snapshots:
            self.logger.warning("Rollback snapshot not found", snapshot_id=snapshot_id)
            return None

        snapshot = self._rollback_snapshots[snapshot_id]

        if snapshot.is_expired():
            self.logger.warning("Rollback snapshot expired", snapshot_id=snapshot_id)
            return None

        return snapshot

    def log_operation_result(
        self,
        operation: str,
        status: str,
        confirmation_token_id: Optional[str] = None,
        execution_results: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None,
        rollback_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Log an operation result to the audit trail.

        Args:
            operation: Operation name
            status: Operation status
            confirmation_token_id: Associated confirmation token ID
            execution_results: Results of execution
            error_message: Error message if operation failed
            error_details: Detailed error information
            rollback_info: Rollback information if applicable

        Returns:
            Audit log entry ID
        """
        # Get token information if available
        changes = []
        safety_assessment = None
        user_context = {}

        if confirmation_token_id and confirmation_token_id in self._confirmation_tokens:
            token = self._confirmation_tokens[confirmation_token_id]
            changes = token.changes
            safety_assessment = token.safety_assessment
            user_context = token.user_context

        audit_entry = AuditLogEntry(
            operation=operation,
            status=status,
            user_context=user_context,
            changes=changes,
            confirmation_token_id=confirmation_token_id,
            safety_assessment=safety_assessment,
            execution_results=execution_results or {},
            rollback_info=rollback_info,
            error_message=error_message,
            error_details=error_details,
        )

        self._audit_log.append(audit_entry)

        self.logger.info(
            "Operation result logged",
            entry_id=audit_entry.entry_id,
            operation=operation,
            status=status,
        )

        return audit_entry.entry_id

    def get_audit_history(
        self,
        limit: int = 50,
        operation_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get audit history.

        Args:
            limit: Maximum number of entries to return
            operation_filter: Filter by operation type
            status_filter: Filter by status

        Returns:
            List of audit log entries
        """
        entries = self._audit_log.copy()

        # Apply filters
        if operation_filter:
            entries = [e for e in entries if e.operation == operation_filter]

        if status_filter:
            entries = [e for e in entries if e.status == status_filter]

        # Sort by timestamp (newest first) and limit
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        entries = entries[:limit]

        return [entry.model_dump() for entry in entries]

    def cleanup_expired_tokens(self) -> int:
        """Clean up expired confirmation tokens.

        Returns:
            Number of tokens cleaned up
        """
        expired_tokens = [
            token_id
            for token_id, token in self._confirmation_tokens.items()
            if token.is_expired()
        ]

        for token_id in expired_tokens:
            del self._confirmation_tokens[token_id]

        if expired_tokens:
            self.logger.info("Cleaned up expired tokens", count=len(expired_tokens))

        return len(expired_tokens)

    def cleanup_expired_snapshots(self) -> int:
        """Clean up expired rollback snapshots.

        Returns:
            Number of snapshots cleaned up
        """
        expired_snapshots = [
            snapshot_id
            for snapshot_id, snapshot in self._rollback_snapshots.items()
            if snapshot.is_expired()
        ]

        for snapshot_id in expired_snapshots:
            del self._rollback_snapshots[snapshot_id]

        if expired_snapshots:
            self.logger.info(
                "Cleaned up expired snapshots", count=len(expired_snapshots)
            )

        return len(expired_snapshots)

    def _generate_confirmation_prompt(
        self,
        changes: List[ResourceChange],
        safety_assessment: SafetyAssessment,
    ) -> str:
        """Generate a human-readable confirmation prompt.

        Args:
            changes: List of resource changes
            safety_assessment: Safety assessment for the changes

        Returns:
            Formatted confirmation prompt
        """
        prompt_lines = [
            "🚨 KUBERNETES RESOURCE MODIFICATION CONFIRMATION 🚨",
            "",
            f"Risk Level: {safety_assessment.overall_risk_level.value.upper()} ⚠️",
            f"Resources Affected: {safety_assessment.total_resources_affected}",
            "",
            "CHANGES TO BE APPLIED:",
        ]

        # Add change details
        for i, change in enumerate(
            changes[:10], 1
        ):  # Limit to first 10 for readability
            prompt_lines.extend(
                [
                    f"{i}. {change.object_kind}: {change.object_name} (namespace: {change.namespace})",
                    f"   Current: CPU={change.current_values.get('cpu', 'N/A')}, Memory={change.current_values.get('memory', 'N/A')}",
                    f"   Proposed: CPU={change.proposed_values.get('cpu', 'N/A')}, Memory={change.proposed_values.get('memory', 'N/A')}",
                ]
            )

            if change.cpu_change_percent:
                prompt_lines.append(f"   CPU Change: {change.cpu_change_percent:+.1f}%")
            if change.memory_change_percent:
                prompt_lines.append(
                    f"   Memory Change: {change.memory_change_percent:+.1f}%"
                )

            prompt_lines.append("")

        if len(changes) > 10:
            prompt_lines.append(f"... and {len(changes) - 10} more changes")
            prompt_lines.append("")

        # Add safety warnings
        if safety_assessment.warnings:
            prompt_lines.extend(
                [
                    "⚠️  SAFETY WARNINGS:",
                ]
            )

            for warning in safety_assessment.warnings[:5]:  # Limit to first 5 warnings
                prompt_lines.append(
                    f"  - {warning.level.value.upper()}: {warning.message}"
                )

            if len(safety_assessment.warnings) > 5:
                prompt_lines.append(
                    f"  ... and {len(safety_assessment.warnings) - 5} more warnings"
                )

            prompt_lines.append("")

        # Add recommendations
        recommendations = []
        if safety_assessment.requires_gradual_rollout:
            recommendations.append("Consider gradual rollout")
        if safety_assessment.requires_monitoring:
            recommendations.append("Enhanced monitoring recommended")
        if safety_assessment.requires_backup:
            recommendations.append("Backup recommended before execution")

        if recommendations:
            prompt_lines.extend(
                [
                    "📋 RECOMMENDATIONS:",
                    *[f"  - {rec}" for rec in recommendations],
                    "",
                ]
            )

        # Add production namespace warning
        if safety_assessment.production_namespaces_affected:
            prompt_lines.extend(
                [
                    "🏭 PRODUCTION NAMESPACES AFFECTED:",
                    f"  {', '.join(safety_assessment.production_namespaces_affected)}",
                    "",
                ]
            )

        prompt_lines.extend(
            [
                "Do you want to proceed with these changes?",
                "Type 'yes' to confirm, or 'no' to cancel.",
                "",
                "⏰ This confirmation will expire in a few minutes.",
            ]
        )

        return "\n".join(prompt_lines)

    def _generate_changes_summary(
        self, changes: List[ResourceChange]
    ) -> Dict[str, Any]:
        """Generate a structured summary of changes.

        Args:
            changes: List of resource changes

        Returns:
            Dictionary with change summary
        """
        summary: Dict[str, Any] = {
            "total_changes": len(changes),
            "by_kind": {},
            "by_namespace": {},
            "by_change_type": {},
            "resource_impact": {
                "cpu_increases": 0,
                "cpu_decreases": 0,
                "memory_increases": 0,
                "memory_decreases": 0,
            },
        }

        for change in changes:
            # Count by kind
            kind = change.object_kind
            summary["by_kind"][kind] = summary["by_kind"].get(kind, 0) + 1

            # Count by namespace
            namespace = change.namespace
            summary["by_namespace"][namespace] = (
                summary["by_namespace"].get(namespace, 0) + 1
            )

            # Count by change type
            change_type = change.change_type.value
            summary["by_change_type"][change_type] = (
                summary["by_change_type"].get(change_type, 0) + 1
            )

            # Count resource impacts
            if change.cpu_change_percent:
                if change.cpu_change_percent > 0:
                    summary["resource_impact"]["cpu_increases"] += 1
                else:
                    summary["resource_impact"]["cpu_decreases"] += 1

            if change.memory_change_percent:
                if change.memory_change_percent > 0:
                    summary["resource_impact"]["memory_increases"] += 1
                else:
                    summary["resource_impact"]["memory_decreases"] += 1

        return summary
