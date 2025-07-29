"""Recommendation models for KRR MCP Server.

This module defines data models for krr recommendations, filtering,
and caching functionality.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KrrStrategy(str, Enum):
    """krr recommendation strategies."""

    SIMPLE = "simple"
    SIMPLE_LIMIT = "simple-limit"


class ResourceType(str, Enum):
    """Types of Kubernetes resources."""

    CPU = "cpu"
    MEMORY = "memory"


class RecommendationSeverity(str, Enum):
    """Severity levels for recommendations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class KubernetesObject(BaseModel):
    """Represents a Kubernetes object reference."""

    kind: str = Field(..., description="Kubernetes object kind (e.g., Deployment)")
    name: str = Field(..., description="Object name")
    namespace: str = Field(..., description="Kubernetes namespace")

    def __str__(self) -> str:
        """String representation of the object."""
        return f"{self.kind}/{self.name} (namespace: {self.namespace})"


class ResourceValue(BaseModel):
    """Represents a resource value (CPU/Memory)."""

    cpu: Optional[str] = Field(None, description="CPU value (e.g., '250m')")
    memory: Optional[str] = Field(None, description="Memory value (e.g., '256Mi')")

    def is_empty(self) -> bool:
        """Check if both CPU and memory are None."""
        return self.cpu is None and self.memory is None


class KrrRecommendation(BaseModel):
    """Represents a single krr recommendation."""

    # Object information
    object: KubernetesObject = Field(..., description="Target Kubernetes object")

    # Resource values
    current_requests: ResourceValue = Field(
        ..., description="Current resource requests"
    )
    current_limits: ResourceValue = Field(..., description="Current resource limits")
    recommended_requests: ResourceValue = Field(
        ..., description="Recommended resource requests"
    )
    recommended_limits: ResourceValue = Field(
        ..., description="Recommended resource limits"
    )

    # Recommendation metadata
    severity: RecommendationSeverity = Field(
        RecommendationSeverity.MEDIUM, description="Recommendation severity"
    )
    potential_savings: Optional[float] = Field(
        None, description="Potential cost savings estimate"
    )
    confidence_score: Optional[float] = Field(
        None, description="Confidence in recommendation (0.0-1.0)"
    )

    # Analysis details
    analysis_period: Optional[str] = Field(
        None, description="Period analyzed (e.g., '7d')"
    )
    cpu_usage_percentile: Optional[float] = Field(
        None, description="CPU usage percentile analyzed"
    )
    memory_usage_percentile: Optional[float] = Field(
        None, description="Memory usage percentile analyzed"
    )

    def calculate_impact(self) -> Dict[str, Any]:
        """Calculate the impact of applying this recommendation."""
        impact: Dict[str, Any] = {
            "cpu_change": None,
            "memory_change": None,
            "cpu_change_percent": None,
            "memory_change_percent": None,
        }

        # Calculate CPU impact
        if self.current_requests.cpu and self.recommended_requests.cpu:
            current_cpu = self._parse_cpu_value(self.current_requests.cpu)
            recommended_cpu = self._parse_cpu_value(self.recommended_requests.cpu)

            if current_cpu and recommended_cpu:
                impact["cpu_change"] = recommended_cpu - current_cpu
                if current_cpu > 0:
                    impact["cpu_change_percent"] = (
                        (recommended_cpu - current_cpu) / current_cpu
                    ) * 100

        # Calculate memory impact
        if self.current_requests.memory and self.recommended_requests.memory:
            current_memory = self._parse_memory_value(self.current_requests.memory)
            recommended_memory = self._parse_memory_value(
                self.recommended_requests.memory
            )

            if current_memory and recommended_memory:
                impact["memory_change"] = recommended_memory - current_memory
                if current_memory > 0:
                    impact["memory_change_percent"] = (
                        (recommended_memory - current_memory) / current_memory
                    ) * 100

        return impact

    def _parse_cpu_value(self, cpu_str: str) -> Optional[float]:
        """Parse CPU value to millicores."""
        if not cpu_str:
            return None

        if cpu_str.endswith("m"):
            return float(cpu_str[:-1])
        else:
            return float(cpu_str) * 1000

    def _parse_memory_value(self, memory_str: str) -> Optional[float]:
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


class RecommendationFilter(BaseModel):
    """Filter criteria for recommendations."""

    namespace: Optional[str] = Field(None, description="Filter by namespace")
    object_kind: Optional[str] = Field(None, description="Filter by object kind")
    object_name_pattern: Optional[str] = Field(
        None, description="Filter by object name pattern"
    )
    resource_type: Optional[ResourceType] = Field(
        None, description="Filter by resource type"
    )
    severity: Optional[RecommendationSeverity] = Field(
        None, description="Filter by severity"
    )
    min_potential_savings: Optional[float] = Field(
        None, description="Minimum potential savings"
    )
    min_confidence_score: Optional[float] = Field(
        None, description="Minimum confidence score"
    )


class KrrScanResult(BaseModel):
    """Result of a krr scan operation."""

    # Scan metadata
    scan_id: str = Field(..., description="Unique scan identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Scan timestamp"
    )
    strategy: KrrStrategy = Field(..., description="Strategy used for scan")

    # Cluster information
    cluster_context: str = Field(..., description="Kubernetes cluster context")
    prometheus_url: str = Field(..., description="Prometheus server URL")

    # Scan parameters
    namespaces_scanned: List[str] = Field(
        ..., description="Namespaces included in scan"
    )
    analysis_period: str = Field(..., description="Historical period analyzed")

    # Results
    recommendations: List[KrrRecommendation] = Field(
        ..., description="Generated recommendations"
    )
    total_recommendations: int = Field(
        ..., description="Total number of recommendations"
    )

    # Summary statistics
    potential_total_savings: Optional[float] = Field(
        None, description="Total potential savings"
    )
    recommendations_by_severity: Dict[str, int] = Field(
        default_factory=dict, description="Count by severity"
    )

    # Execution metadata
    scan_duration_seconds: Optional[float] = Field(
        None, description="Time taken for scan"
    )
    krr_version: Optional[str] = Field(None, description="Version of krr used")

    def calculate_summary(self) -> None:
        """Calculate summary statistics from recommendations."""
        # Count by severity
        severity_counts: Dict[str, int] = {}
        total_savings = 0.0

        for rec in self.recommendations:
            severity = rec.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

            if rec.potential_savings:
                total_savings += rec.potential_savings

        self.recommendations_by_severity = severity_counts
        self.potential_total_savings = total_savings if total_savings > 0 else None
        self.total_recommendations = len(self.recommendations)

    def filter_recommendations(
        self, filter_criteria: RecommendationFilter
    ) -> List[KrrRecommendation]:
        """Filter recommendations based on criteria."""
        filtered = self.recommendations

        if filter_criteria.namespace:
            filtered = [
                r for r in filtered if r.object.namespace == filter_criteria.namespace
            ]

        if filter_criteria.object_kind:
            filtered = [
                r for r in filtered if r.object.kind == filter_criteria.object_kind
            ]

        if filter_criteria.object_name_pattern:
            import re

            pattern = re.compile(filter_criteria.object_name_pattern)
            filtered = [r for r in filtered if pattern.search(r.object.name)]

        if filter_criteria.severity:
            filtered = [r for r in filtered if r.severity == filter_criteria.severity]

        if filter_criteria.min_potential_savings:
            filtered = [
                r
                for r in filtered
                if r.potential_savings
                and r.potential_savings >= filter_criteria.min_potential_savings
            ]

        if filter_criteria.min_confidence_score:
            filtered = [
                r
                for r in filtered
                if r.confidence_score
                and r.confidence_score >= filter_criteria.min_confidence_score
            ]

        return filtered


class CachedScanResult(BaseModel):
    """Represents a cached scan result with TTL."""

    cache_key: str = Field(..., description="Unique cache key")
    scan_result: KrrScanResult = Field(..., description="Cached scan result")
    cached_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Cache timestamp",
    )
    ttl_seconds: int = Field(default=300, description="Time to live in seconds")

    def is_expired(self) -> bool:
        """Check if the cached result has expired."""
        from datetime import timedelta

        expires_at = self.cached_at + timedelta(seconds=self.ttl_seconds)
        return datetime.now(timezone.utc) > expires_at


class KrrError(Exception):
    """Base exception for krr-related errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "KRR_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


class KrrNotFoundError(KrrError):
    """Raised when krr executable is not found."""

    def __init__(self, message: str = "krr executable not found in PATH"):
        super().__init__(message, "KRR_NOT_FOUND")


class KrrVersionError(KrrError):
    """Raised when krr version is incompatible."""

    def __init__(
        self,
        message: str,
        current_version: Optional[str] = None,
        required_version: Optional[str] = None,
    ):
        super().__init__(message, "KRR_VERSION_ERROR")
        self.details = {
            "current_version": current_version,
            "required_version": required_version,
        }


class KrrExecutionError(KrrError):
    """Raised when krr command execution fails."""

    def __init__(self, message: str, exit_code: int, stderr: Optional[str] = None):
        super().__init__(message, "KRR_EXECUTION_ERROR")
        self.details = {
            "exit_code": exit_code,
            "stderr": stderr,
        }


class PrometheusConnectionError(KrrError):
    """Raised when Prometheus connection fails."""

    def __init__(self, message: str, prometheus_url: str):
        super().__init__(message, "PROMETHEUS_CONNECTION_ERROR")
        self.details = {"prometheus_url": prometheus_url}


class KubernetesContextError(KrrError):
    """Raised when Kubernetes context is invalid."""

    def __init__(self, message: str, context: Optional[str] = None):
        super().__init__(message, "KUBERNETES_CONTEXT_ERROR")
        self.details = {"context": context}
