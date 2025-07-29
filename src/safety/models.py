"""Safety models for KRR MCP Server.

This module defines data models for safety-critical operations including
confirmation workflows, risk assessment, and audit trail management.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class RiskLevel(str, Enum):
    """Risk levels for operations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeType(str, Enum):
    """Types of changes that can be made."""

    RESOURCE_INCREASE = "resource_increase"
    RESOURCE_DECREASE = "resource_decrease"
    REPLICA_CHANGE = "replica_change"
    CONFIGURATION_CHANGE = "configuration_change"


class ResourceChange(BaseModel):
    """Represents a single resource change."""

    object_kind: str = Field(
        ..., description="Kubernetes object kind (e.g., Deployment)"
    )
    object_name: str = Field(..., description="Name of the Kubernetes object")
    namespace: str = Field(..., description="Kubernetes namespace")

    change_type: ChangeType = Field(..., description="Type of change being made")

    current_values: Dict[str, Any] = Field(..., description="Current resource values")
    proposed_values: Dict[str, Any] = Field(..., description="Proposed resource values")

    # Calculated fields
    cpu_change_percent: Optional[float] = Field(
        None, description="CPU change percentage"
    )
    memory_change_percent: Optional[float] = Field(
        None, description="Memory change percentage"
    )

    estimated_cost_impact: Optional[float] = Field(
        None, description="Estimated monthly cost impact"
    )

    def calculate_impact(self) -> None:
        """Calculate the impact of this change."""
        # Calculate CPU change percentage
        current_cpu = self._parse_cpu_value(self.current_values.get("cpu"))
        proposed_cpu = self._parse_cpu_value(self.proposed_values.get("cpu"))

        if current_cpu and proposed_cpu and current_cpu > 0:
            self.cpu_change_percent = ((proposed_cpu - current_cpu) / current_cpu) * 100

        # Calculate memory change percentage
        current_memory = self._parse_memory_value(self.current_values.get("memory"))
        proposed_memory = self._parse_memory_value(self.proposed_values.get("memory"))

        if current_memory and proposed_memory and current_memory > 0:
            self.memory_change_percent = (
                (proposed_memory - current_memory) / current_memory
            ) * 100

    def _parse_cpu_value(self, cpu_str: Optional[str]) -> Optional[float]:
        """Parse CPU value to millicores."""
        if not cpu_str:
            return None

        if cpu_str.endswith("m"):
            return float(cpu_str[:-1])
        else:
            return float(cpu_str) * 1000

    def _parse_memory_value(self, memory_str: Optional[str]) -> Optional[float]:
        """Parse memory value to bytes."""
        if not memory_str:
            return None

        multipliers = {
            "Ki": 1024,
            "Mi": 1024**2,
            "Gi": 1024**3,
            "Ti": 1024**4,
        }

        for suffix, multiplier in multipliers.items():
            if memory_str.endswith(suffix):
                return float(memory_str[: -len(suffix)]) * multiplier

        # Assume bytes if no suffix
        return float(memory_str)


class SafetyWarning(BaseModel):
    """Represents a safety warning for a proposed change."""

    level: RiskLevel = Field(..., description="Warning severity level")
    message: str = Field(..., description="Human-readable warning message")
    recommendation: str = Field(..., description="Recommended action")

    # Additional context
    affected_object: str = Field(..., description="Object that triggered this warning")
    change_details: Dict[str, Any] = Field(
        default_factory=dict, description="Details about the change"
    )


class SafetyAssessment(BaseModel):
    """Comprehensive safety assessment for a set of changes."""

    overall_risk_level: RiskLevel = Field(..., description="Overall risk level")
    total_resources_affected: int = Field(
        ..., description="Total number of resources affected"
    )

    warnings: List[SafetyWarning] = Field(
        default_factory=list, description="List of safety warnings"
    )

    # Impact summary
    total_cpu_change_percent: Optional[float] = Field(
        None, description="Total CPU change percentage"
    )
    total_memory_change_percent: Optional[float] = Field(
        None, description="Total memory change percentage"
    )
    estimated_monthly_cost_change: Optional[float] = Field(
        None, description="Estimated monthly cost change"
    )

    # Safety metrics
    high_impact_changes: int = Field(0, description="Number of high-impact changes")
    critical_workloads_affected: int = Field(
        0, description="Number of critical workloads affected"
    )
    production_namespaces_affected: List[str] = Field(
        default_factory=list, description="Production namespaces affected"
    )

    # Recommendations
    requires_gradual_rollout: bool = Field(
        False, description="Whether gradual rollout is recommended"
    )
    requires_monitoring: bool = Field(
        False, description="Whether enhanced monitoring is required"
    )
    requires_backup: bool = Field(
        False, description="Whether backup is required before execution"
    )


class ConfirmationToken(BaseModel):
    """Represents a confirmation token for user approval."""

    token_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique token ID"
    )
    secret: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret token value",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Token creation time",
    )
    expires_at: datetime = Field(..., description="Token expiration time")

    # Associated data
    changes: List[ResourceChange] = Field(
        ..., description="Changes this token authorizes"
    )
    safety_assessment: SafetyAssessment = Field(
        ..., description="Safety assessment for these changes"
    )

    # Usage tracking
    used: bool = Field(False, description="Whether this token has been used")
    used_at: Optional[datetime] = Field(None, description="When this token was used")

    # User context
    user_context: Dict[str, Any] = Field(
        default_factory=dict, description="Additional user context"
    )

    @model_validator(mode="before")
    @classmethod
    def set_expires_at(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Set expiration time if not provided."""
        if isinstance(values, dict) and "expires_at" not in values:
            created_at = values.get("created_at", datetime.now(timezone.utc))
            values["expires_at"] = created_at + timedelta(
                minutes=5
            )  # Default 5-minute expiration
        return values

    def is_expired(self) -> bool:
        """Check if the token has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def is_valid(self) -> bool:
        """Check if the token is valid for use."""
        return not self.used and not self.is_expired()

    def mark_used(self) -> None:
        """Mark the token as used."""
        self.used = True
        self.used_at = datetime.now(timezone.utc)


class AuditLogEntry(BaseModel):
    """Represents an audit log entry."""

    entry_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique entry ID"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Entry timestamp",
    )

    # Operation details
    operation: str = Field(..., description="Operation performed")
    status: str = Field(
        ...,
        description="Operation status (requested, approved, executed, failed, rolled_back)",
    )

    # User and context
    user_context: Dict[str, Any] = Field(
        default_factory=dict, description="User context information"
    )
    cluster_context: Dict[str, str] = Field(
        default_factory=dict, description="Cluster context"
    )

    # Changes and confirmations
    changes: List[ResourceChange] = Field(
        default_factory=list, description="Changes involved in this operation"
    )
    confirmation_token_id: Optional[str] = Field(
        None, description="Associated confirmation token ID"
    )
    safety_assessment: Optional[SafetyAssessment] = Field(
        None, description="Safety assessment"
    )

    # Results
    execution_results: Dict[str, Any] = Field(
        default_factory=dict, description="Execution results"
    )
    rollback_info: Optional[Dict[str, Any]] = Field(
        None, description="Rollback information if applicable"
    )

    # Error information
    error_message: Optional[str] = Field(
        None, description="Error message if operation failed"
    )
    error_details: Optional[Dict[str, Any]] = Field(
        None, description="Detailed error information"
    )


class RollbackSnapshot(BaseModel):
    """Represents a snapshot for rollback purposes."""

    snapshot_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique snapshot ID"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Snapshot creation time",
    )
    expires_at: datetime = Field(..., description="Snapshot expiration time")

    # Associated operation
    operation_id: str = Field(
        ..., description="ID of the operation this snapshot is for"
    )
    confirmation_token_id: str = Field(
        ..., description="Associated confirmation token ID"
    )

    # Snapshot data
    original_manifests: List[Dict[str, Any]] = Field(
        ..., description="Original Kubernetes manifests"
    )
    rollback_commands: List[str] = Field(
        ..., description="Commands to execute rollback"
    )

    # Metadata
    cluster_context: Dict[str, str] = Field(
        ..., description="Cluster context at time of snapshot"
    )
    affected_resources: List[Dict[str, str]] = Field(
        ..., description="List of affected resources"
    )

    @model_validator(mode="before")
    @classmethod
    def set_defaults(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Set default values if not provided."""
        if isinstance(values, dict):
            # Set default expiration time
            if "expires_at" not in values:
                created_at = values.get("created_at", datetime.now(timezone.utc))
                values["expires_at"] = created_at + timedelta(
                    days=7
                )  # Default 7-day retention

            # Set affected_resources from original_manifests if not provided
            if "affected_resources" not in values and "original_manifests" in values:
                values["affected_resources"] = [
                    {
                        "kind": manifest.get("kind", "Unknown"),
                        "name": manifest.get("metadata", {}).get("name", "Unknown"),
                        "namespace": manifest.get("metadata", {}).get(
                            "namespace", "default"
                        ),
                    }
                    for manifest in values["original_manifests"]
                ]
        return values

    def is_expired(self) -> bool:
        """Check if the snapshot has expired."""
        return datetime.now(timezone.utc) > self.expires_at
