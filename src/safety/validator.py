"""Safety validation engine for KRR MCP Server.

This module implements comprehensive safety checks and validation logic
to prevent dangerous cluster modifications.
"""

import re
from typing import Dict, List, Set, Tuple

import structlog

from .models import (
    ChangeType,
    ResourceChange,
    RiskLevel,
    SafetyAssessment,
    SafetyWarning,
)

logger = structlog.get_logger(__name__)


class SafetyConfig:
    """Configuration for safety validation."""
    
    # Resource change limits
    MAX_CPU_INCREASE_PERCENT = 500  # 500% max increase
    MAX_MEMORY_INCREASE_PERCENT = 500  # 500% max increase
    HIGH_IMPACT_THRESHOLD_PERCENT = 100  # Changes >100% are high impact
    
    # Critical workload patterns
    CRITICAL_WORKLOAD_PATTERNS = [
        r".*prod.*",
        r".*production.*",
        r".*critical.*",
        r".*database.*",
        r".*db.*",
        r".*redis.*",
        r".*etcd.*",
        r".*ingress.*",
        r".*controller.*",
    ]
    
    # Production namespace patterns  
    PRODUCTION_NAMESPACE_PATTERNS = [
        r"^prod.*",
        r"^production.*",
        r".*-prod$",
        r".*-production$",
        r"^default$",  # Default namespace often contains production workloads
    ]
    
    # Gradual rollout triggers
    GRADUAL_ROLLOUT_TRIGGERS = {
        "high_replica_count": 5,  # Workloads with >5 replicas
        "large_resource_change": 200,  # Changes >200%
        "multiple_critical_workloads": 3,  # >3 critical workloads affected
    }


class SafetyValidator:
    """Validates proposed changes for safety issues."""
    
    def __init__(self, config: SafetyConfig = None):
        """Initialize the safety validator.
        
        Args:
            config: Safety configuration, uses defaults if not provided
        """
        self.config = config or SafetyConfig()
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    def validate_changes(self, changes: List[ResourceChange]) -> SafetyAssessment:
        """Validate a list of proposed changes.
        
        Args:
            changes: List of resource changes to validate
            
        Returns:
            SafetyAssessment with validation results
        """
        self.logger.info("Validating changes", change_count=len(changes))
        
        # Calculate impact for all changes
        for change in changes:
            change.calculate_impact()
        
        warnings = []
        
        # Run all validation checks
        warnings.extend(self._check_resource_limits(changes))
        warnings.extend(self._check_critical_workloads(changes))
        warnings.extend(self._check_production_namespaces(changes))
        warnings.extend(self._check_extreme_changes(changes))
        warnings.extend(self._check_simultaneous_changes(changes))
        
        # Analyze overall risk
        overall_risk = self._assess_overall_risk(warnings)
        
        # Count high-impact changes
        high_impact_changes = sum(
            1 for change in changes
            if self._is_high_impact_change(change)
        )
        
        # Identify critical workloads
        critical_workloads = self._count_critical_workloads(changes)
        
        # Identify production namespaces
        prod_namespaces = self._get_production_namespaces(changes)
        
        # Calculate total impact
        total_cpu_change = self._calculate_total_cpu_change(changes)
        total_memory_change = self._calculate_total_memory_change(changes)
        
        # Create assessment
        assessment = SafetyAssessment(
            overall_risk_level=overall_risk,
            total_resources_affected=len(changes),
            warnings=warnings,
            total_cpu_change_percent=total_cpu_change,
            total_memory_change_percent=total_memory_change,
            high_impact_changes=high_impact_changes,
            critical_workloads_affected=critical_workloads,
            production_namespaces_affected=prod_namespaces,
            requires_gradual_rollout=self._requires_gradual_rollout(changes, warnings),
            requires_monitoring=self._requires_monitoring(changes, warnings),
            requires_backup=self._requires_backup(changes, warnings),
        )
        
        self.logger.info(
            "Safety validation completed",
            overall_risk=overall_risk.value,
            warning_count=len(warnings),
            high_impact_changes=high_impact_changes,
        )
        
        return assessment
    
    def _check_resource_limits(self, changes: List[ResourceChange]) -> List[SafetyWarning]:
        """Check for resource limit violations."""
        warnings = []
        
        for change in changes:
            # Check CPU limits
            if change.cpu_change_percent and change.cpu_change_percent > self.config.MAX_CPU_INCREASE_PERCENT:
                warnings.append(SafetyWarning(
                    level=RiskLevel.CRITICAL,
                    message=f"CPU increase of {change.cpu_change_percent:.1f}% exceeds maximum allowed ({self.config.MAX_CPU_INCREASE_PERCENT}%)",
                    recommendation="Consider a smaller increase or gradual rollout",
                    affected_object=f"{change.object_kind}/{change.object_name}",
                    change_details={"cpu_change_percent": change.cpu_change_percent}
                ))
            
            # Check memory limits
            if change.memory_change_percent and change.memory_change_percent > self.config.MAX_MEMORY_INCREASE_PERCENT:
                warnings.append(SafetyWarning(
                    level=RiskLevel.CRITICAL,
                    message=f"Memory increase of {change.memory_change_percent:.1f}% exceeds maximum allowed ({self.config.MAX_MEMORY_INCREASE_PERCENT}%)",
                    recommendation="Consider a smaller increase or gradual rollout",
                    affected_object=f"{change.object_kind}/{change.object_name}",
                    change_details={"memory_change_percent": change.memory_change_percent}
                ))
        
        return warnings
    
    def _check_critical_workloads(self, changes: List[ResourceChange]) -> List[SafetyWarning]:
        """Check for changes to critical workloads."""
        warnings = []
        
        for change in changes:
            workload_name = change.object_name.lower()
            
            # Check if workload matches critical patterns
            for pattern in self.config.CRITICAL_WORKLOAD_PATTERNS:
                if re.match(pattern, workload_name):
                    warnings.append(SafetyWarning(
                        level=RiskLevel.HIGH,
                        message=f"Modifying critical workload: {change.object_name}",
                        recommendation="Exercise extra caution and consider gradual rollout",
                        affected_object=f"{change.object_kind}/{change.object_name}",
                        change_details={"matched_pattern": pattern}
                    ))
                    break
        
        return warnings
    
    def _check_production_namespaces(self, changes: List[ResourceChange]) -> List[SafetyWarning]:
        """Check for changes in production namespaces."""
        warnings = []
        
        for change in changes:
            namespace = change.namespace.lower()
            
            # Check if namespace matches production patterns
            for pattern in self.config.PRODUCTION_NAMESPACE_PATTERNS:
                if re.match(pattern, namespace):
                    warnings.append(SafetyWarning(
                        level=RiskLevel.HIGH,
                        message=f"Modifying resources in production namespace: {change.namespace}",
                        recommendation="Ensure proper approval and monitoring",
                        affected_object=f"{change.object_kind}/{change.object_name}",
                        change_details={"namespace": change.namespace}
                    ))
                    break
        
        return warnings
    
    def _check_extreme_changes(self, changes: List[ResourceChange]) -> List[SafetyWarning]:
        """Check for extremely large resource changes."""
        warnings = []
        
        for change in changes:
            extreme_changes = []
            
            # Check for extreme CPU changes
            if change.cpu_change_percent:
                if change.cpu_change_percent > 1000:  # >1000% increase
                    extreme_changes.append(f"CPU: {change.cpu_change_percent:.1f}%")
                elif change.cpu_change_percent < -90:  # >90% decrease
                    extreme_changes.append(f"CPU: {change.cpu_change_percent:.1f}%")
            
            # Check for extreme memory changes
            if change.memory_change_percent:
                if change.memory_change_percent > 1000:  # >1000% increase
                    extreme_changes.append(f"Memory: {change.memory_change_percent:.1f}%")
                elif change.memory_change_percent < -90:  # >90% decrease
                    extreme_changes.append(f"Memory: {change.memory_change_percent:.1f}%")
            
            if extreme_changes:
                warnings.append(SafetyWarning(
                    level=RiskLevel.CRITICAL,
                    message=f"Extreme resource changes detected: {', '.join(extreme_changes)}",
                    recommendation="Verify these changes are intentional and necessary",
                    affected_object=f"{change.object_kind}/{change.object_name}",
                    change_details={"extreme_changes": extreme_changes}
                ))
        
        return warnings
    
    def _check_simultaneous_changes(self, changes: List[ResourceChange]) -> List[SafetyWarning]:
        """Check for potentially risky simultaneous changes."""
        warnings = []
        
        # Check for too many simultaneous changes
        if len(changes) > 20:  # Arbitrary threshold
            warnings.append(SafetyWarning(
                level=RiskLevel.MEDIUM,
                message=f"Large number of simultaneous changes: {len(changes)} resources",
                recommendation="Consider executing changes in smaller batches",
                affected_object="multiple",
                change_details={"total_changes": len(changes)}
            ))
        
        # Check for changes to multiple critical namespaces
        critical_namespaces = set()
        for change in changes:
            if any(re.match(pattern, change.namespace.lower()) for pattern in self.config.PRODUCTION_NAMESPACE_PATTERNS):
                critical_namespaces.add(change.namespace)
        
        if len(critical_namespaces) > 3:
            warnings.append(SafetyWarning(
                level=RiskLevel.HIGH,
                message=f"Changes affect multiple production namespaces: {', '.join(critical_namespaces)}",
                recommendation="Consider staging changes across namespaces",
                affected_object="multiple",
                change_details={"affected_namespaces": list(critical_namespaces)}
            ))
        
        return warnings
    
    def _assess_overall_risk(self, warnings: List[SafetyWarning]) -> RiskLevel:
        """Assess overall risk level based on warnings."""
        if any(w.level == RiskLevel.CRITICAL for w in warnings):
            return RiskLevel.CRITICAL
        elif any(w.level == RiskLevel.HIGH for w in warnings):
            return RiskLevel.HIGH
        elif any(w.level == RiskLevel.MEDIUM for w in warnings):
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _is_high_impact_change(self, change: ResourceChange) -> bool:
        """Check if a change is high impact."""
        if change.cpu_change_percent and abs(change.cpu_change_percent) > self.config.HIGH_IMPACT_THRESHOLD_PERCENT:
            return True
        if change.memory_change_percent and abs(change.memory_change_percent) > self.config.HIGH_IMPACT_THRESHOLD_PERCENT:
            return True
        return False
    
    def _count_critical_workloads(self, changes: List[ResourceChange]) -> int:
        """Count the number of critical workloads affected."""
        critical_count = 0
        
        for change in changes:
            workload_name = change.object_name.lower()
            if any(re.match(pattern, workload_name) for pattern in self.config.CRITICAL_WORKLOAD_PATTERNS):
                critical_count += 1
        
        return critical_count
    
    def _get_production_namespaces(self, changes: List[ResourceChange]) -> List[str]:
        """Get list of production namespaces affected."""
        prod_namespaces = set()
        
        for change in changes:
            namespace = change.namespace.lower()
            if any(re.match(pattern, namespace) for pattern in self.config.PRODUCTION_NAMESPACE_PATTERNS):
                prod_namespaces.add(change.namespace)
        
        return list(prod_namespaces)
    
    def _calculate_total_cpu_change(self, changes: List[ResourceChange]) -> float:
        """Calculate total CPU change percentage."""
        cpu_changes = [c.cpu_change_percent for c in changes if c.cpu_change_percent is not None]
        return sum(cpu_changes) / len(cpu_changes) if cpu_changes else 0.0
    
    def _calculate_total_memory_change(self, changes: List[ResourceChange]) -> float:
        """Calculate total memory change percentage."""
        memory_changes = [c.memory_change_percent for c in changes if c.memory_change_percent is not None]
        return sum(memory_changes) / len(memory_changes) if memory_changes else 0.0
    
    def _requires_gradual_rollout(self, changes: List[ResourceChange], warnings: List[SafetyWarning]) -> bool:
        """Determine if gradual rollout is required."""
        # High number of high-impact changes
        high_impact_count = sum(1 for c in changes if self._is_high_impact_change(c))
        if high_impact_count >= self.config.GRADUAL_ROLLOUT_TRIGGERS["multiple_critical_workloads"]:
            return True
        
        # Large resource changes
        for change in changes:
            if (change.cpu_change_percent and abs(change.cpu_change_percent) > self.config.GRADUAL_ROLLOUT_TRIGGERS["large_resource_change"]) or \
               (change.memory_change_percent and abs(change.memory_change_percent) > self.config.GRADUAL_ROLLOUT_TRIGGERS["large_resource_change"]):
                return True
        
        # Critical warnings present
        if any(w.level == RiskLevel.CRITICAL for w in warnings):
            return True
        
        return False
    
    def _requires_monitoring(self, changes: List[ResourceChange], warnings: List[SafetyWarning]) -> bool:
        """Determine if enhanced monitoring is required."""
        # Always require monitoring for production changes
        prod_namespaces = self._get_production_namespaces(changes)
        if prod_namespaces:
            return True
        
        # Require monitoring for high-impact changes
        if any(self._is_high_impact_change(c) for c in changes):
            return True
        
        # Require monitoring if there are medium or higher warnings
        if any(w.level in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL] for w in warnings):
            return True
        
        return False
    
    def _requires_backup(self, changes: List[ResourceChange], warnings: List[SafetyWarning]) -> bool:
        """Determine if backup is required before execution."""
        # Always require backup for critical warnings
        if any(w.level == RiskLevel.CRITICAL for w in warnings):
            return True
        
        # Require backup for production namespace changes
        prod_namespaces = self._get_production_namespaces(changes)
        if prod_namespaces:
            return True
        
        # Require backup for large number of changes
        if len(changes) > 10:
            return True
        
        return False