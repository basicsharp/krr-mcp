"""Execution models for krr MCP Server.

This module defines data models for kubectl execution,
transaction management, and execution results.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Status of execution operations."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ExecutionMode(str, Enum):
    """Execution modes for applying changes."""
    SINGLE = "single"  # Apply changes one by one
    BATCH = "batch"    # Apply all changes in batch
    STAGED = "staged"  # Staged rollout with canary


class KubectlCommand(BaseModel):
    """Represents a kubectl command to be executed."""
    
    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique command ID")
    operation: str = Field(..., description="kubectl operation (apply, patch, delete)")
    resource_type: str = Field(..., description="Kubernetes resource type")
    resource_name: str = Field(..., description="Resource name")
    namespace: str = Field(..., description="Kubernetes namespace")
    
    # Command details
    kubectl_args: List[str] = Field(..., description="Full kubectl command arguments")
    manifest_content: Optional[str] = Field(None, description="Manifest content if applicable")
    dry_run: bool = Field(False, description="Whether this is a dry-run command")
    
    # Execution metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Command creation time")
    estimated_duration_seconds: Optional[float] = Field(None, description="Estimated execution time")
    
    def __str__(self) -> str:
        """String representation of the command."""
        return f"kubectl {' '.join(self.kubectl_args)}"


class ExecutionResult(BaseModel):
    """Result of executing a kubectl command."""
    
    command_id: str = Field(..., description="Associated command ID")
    status: ExecutionStatus = Field(..., description="Execution status")
    
    # Execution timing
    started_at: datetime = Field(..., description="Execution start time")
    completed_at: Optional[datetime] = Field(None, description="Execution completion time")
    duration_seconds: Optional[float] = Field(None, description="Execution duration")
    
    # Results
    exit_code: int = Field(..., description="Command exit code")
    stdout: str = Field(default="", description="Standard output")
    stderr: str = Field(default="", description="Standard error")
    
    # Resource information
    affected_resources: List[Dict[str, str]] = Field(default_factory=list, description="Resources affected")
    
    # Error details
    error_message: Optional[str] = Field(None, description="Human-readable error message")
    error_details: Dict[str, Any] = Field(default_factory=dict, description="Detailed error information")
    
    def is_successful(self) -> bool:
        """Check if execution was successful."""
        return self.status == ExecutionStatus.COMPLETED and self.exit_code == 0
    
    def calculate_duration(self) -> None:
        """Calculate execution duration if completed."""
        if self.completed_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()


class ExecutionTransaction(BaseModel):
    """Represents a transaction of multiple kubectl operations."""
    
    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique transaction ID")
    confirmation_token_id: str = Field(..., description="Associated confirmation token")
    
    # Transaction metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Transaction creation time")
    started_at: Optional[datetime] = Field(None, description="Transaction start time")
    completed_at: Optional[datetime] = Field(None, description="Transaction completion time")
    
    # Commands and execution
    commands: List[KubectlCommand] = Field(..., description="Commands in this transaction")
    execution_mode: ExecutionMode = Field(ExecutionMode.SINGLE, description="Execution mode")
    dry_run: bool = Field(False, description="Whether this is a dry-run transaction")
    
    # Results
    command_results: List[ExecutionResult] = Field(default_factory=list, description="Results of executed commands")
    overall_status: ExecutionStatus = Field(ExecutionStatus.PENDING, description="Overall transaction status")
    
    # Progress tracking
    commands_completed: int = Field(0, description="Number of commands completed")
    commands_failed: int = Field(0, description="Number of commands failed")
    
    # Rollback information
    rollback_snapshot_id: Optional[str] = Field(None, description="Associated rollback snapshot ID")
    rollback_required: bool = Field(False, description="Whether rollback is required")
    
    def calculate_progress(self) -> Dict[str, Any]:
        """Calculate transaction progress."""
        total_commands = len(self.commands)
        completed = len([r for r in self.command_results if r.status == ExecutionStatus.COMPLETED])
        failed = len([r for r in self.command_results if r.status == ExecutionStatus.FAILED])
        in_progress = len([r for r in self.command_results if r.status == ExecutionStatus.IN_PROGRESS])
        
        progress_percent = (completed / total_commands * 100) if total_commands > 0 else 0
        
        return {
            "total_commands": total_commands,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "pending": total_commands - completed - failed - in_progress,
            "progress_percent": progress_percent,
            "estimated_time_remaining": self._estimate_remaining_time(),
        }
    
    def _estimate_remaining_time(self) -> Optional[float]:
        """Estimate remaining time based on completed commands."""
        completed_results = [r for r in self.command_results if r.duration_seconds is not None]
        
        if not completed_results:
            return None
        
        avg_duration = sum(r.duration_seconds for r in completed_results) / len(completed_results)
        remaining_commands = len(self.commands) - len(self.command_results)
        
        return avg_duration * remaining_commands if remaining_commands > 0 else 0
    
    def get_failed_commands(self) -> List[ExecutionResult]:
        """Get list of failed command results."""
        return [r for r in self.command_results if r.status == ExecutionStatus.FAILED]
    
    def should_continue_on_failure(self) -> bool:
        """Determine if transaction should continue after a failure."""
        # For now, stop on any failure for safety
        # This can be made configurable in the future
        return False


class ExecutionReport(BaseModel):
    """Comprehensive report of execution results."""
    
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique report ID")
    transaction_id: str = Field(..., description="Associated transaction ID")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Report generation time")
    
    # Summary statistics
    total_commands: int = Field(..., description="Total number of commands")
    successful_commands: int = Field(..., description="Number of successful commands")
    failed_commands: int = Field(..., description="Number of failed commands")
    total_duration_seconds: float = Field(..., description="Total execution time")
    
    # Resource impact
    resources_modified: List[Dict[str, str]] = Field(..., description="Resources that were modified")
    namespaces_affected: List[str] = Field(..., description="Namespaces that were affected")
    
    # Detailed results
    command_summaries: List[Dict[str, Any]] = Field(..., description="Summary of each command")
    error_summary: Optional[str] = Field(None, description="Summary of errors if any occurred")
    
    # Recommendations
    recommendations: List[str] = Field(default_factory=list, description="Post-execution recommendations")
    rollback_available: bool = Field(False, description="Whether rollback is available")
    rollback_snapshot_id: Optional[str] = Field(None, description="Rollback snapshot ID if available")
    
    def calculate_success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_commands == 0:
            return 0.0
        return (self.successful_commands / self.total_commands) * 100


class KubectlError(Exception):
    """Base exception for kubectl-related errors."""
    
    def __init__(self, message: str, error_code: str = "KUBECTL_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


class KubectlNotFoundError(KubectlError):
    """Raised when kubectl executable is not found."""
    
    def __init__(self, message: str = "kubectl executable not found in PATH"):
        super().__init__(message, "KUBECTL_NOT_FOUND")


class KubectlContextError(KubectlError):
    """Raised when kubectl context is invalid."""
    
    def __init__(self, message: str, context: Optional[str] = None):
        super().__init__(message, "KUBECTL_CONTEXT_ERROR")
        self.details = {"context": context}


class KubectlExecutionError(KubectlError):
    """Raised when kubectl command execution fails."""
    
    def __init__(self, message: str, exit_code: int, stderr: Optional[str] = None, command: Optional[str] = None):
        super().__init__(message, "KUBECTL_EXECUTION_ERROR")
        self.details = {
            "exit_code": exit_code,
            "stderr": stderr,
            "command": command,
        }


class KubectlTimeoutError(KubectlError):
    """Raised when kubectl command times out."""
    
    def __init__(self, message: str, timeout_seconds: int, command: Optional[str] = None):
        super().__init__(message, "KUBECTL_TIMEOUT_ERROR")
        self.details = {
            "timeout_seconds": timeout_seconds,
            "command": command,
        }


class KubectlResourceNotFoundError(KubectlError):
    """Raised when a Kubernetes resource is not found."""
    
    def __init__(self, message: str, resource_type: str, resource_name: str, namespace: str):
        super().__init__(message, "KUBECTL_RESOURCE_NOT_FOUND")
        self.details = {
            "resource_type": resource_type,
            "resource_name": resource_name,
            "namespace": namespace,
        }


class KubectlPermissionError(KubectlError):
    """Raised when kubectl lacks permissions for an operation."""
    
    def __init__(self, message: str, operation: str, resource: str):
        super().__init__(message, "KUBECTL_PERMISSION_ERROR")
        self.details = {
            "operation": operation,
            "resource": resource,
        }