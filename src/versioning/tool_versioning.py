"""Tool versioning system for MCP tools.

This module provides version management for MCP tools, enabling
backward compatibility, deprecation warnings, and smooth upgrades.
"""

import functools
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class VersionStatus(Enum):
    """Version status indicators."""

    CURRENT = "current"
    SUPPORTED = "supported"
    DEPRECATED = "deprecated"
    UNSUPPORTED = "unsupported"


class ToolVersion(BaseModel):
    """Tool version information."""

    version: str = Field(description="Semantic version string (e.g., '1.0.0')")
    status: VersionStatus = Field(description="Version status")
    introduced_at: datetime = Field(description="When this version was introduced")
    deprecated_at: Optional[datetime] = Field(
        None, description="When this version was deprecated"
    )
    sunset_at: Optional[datetime] = Field(
        None, description="When this version will be removed"
    )
    breaking_changes: List[str] = Field(
        default_factory=list, description="List of breaking changes"
    )
    migration_notes: Optional[str] = Field(
        None, description="Migration guidance for upgrading"
    )
    changelog: List[str] = Field(default_factory=list, description="Version changelog")


class ToolVersionRegistry:
    """Registry for managing tool versions."""

    def __init__(self) -> None:
        """Initialize the version registry."""
        self.tools: Dict[str, Dict[str, ToolVersion]] = {}
        self.logger = structlog.get_logger(self.__class__.__name__)

    def register_version(
        self,
        tool_name: str,
        version: str,
        status: VersionStatus = VersionStatus.CURRENT,
        breaking_changes: Optional[List[str]] = None,
        migration_notes: Optional[str] = None,
        changelog: Optional[List[str]] = None,
    ) -> None:
        """Register a new version for a tool.

        Args:
            tool_name: Name of the MCP tool
            version: Semantic version string
            status: Version status
            breaking_changes: List of breaking changes in this version
            migration_notes: Migration guidance for upgrading
            changelog: List of changes in this version
        """
        if tool_name not in self.tools:
            self.tools[tool_name] = {}

        tool_version = ToolVersion(
            version=version,
            status=status,
            introduced_at=datetime.now(timezone.utc),
            deprecated_at=None,
            sunset_at=None,
            breaking_changes=breaking_changes or [],
            migration_notes=migration_notes,
            changelog=changelog or [],
        )

        self.tools[tool_name][version] = tool_version

        self.logger.info(
            "Registered tool version",
            tool_name=tool_name,
            version=version,
            status=status.value,
        )

    def deprecate_version(
        self,
        tool_name: str,
        version: str,
        sunset_date: Optional[datetime] = None,
        migration_notes: Optional[str] = None,
    ) -> None:
        """Mark a tool version as deprecated.

        Args:
            tool_name: Name of the MCP tool
            version: Version to deprecate
            sunset_date: When the version will be removed
            migration_notes: Migration guidance
        """
        if tool_name in self.tools and version in self.tools[tool_name]:
            tool_version = self.tools[tool_name][version]
            tool_version.status = VersionStatus.DEPRECATED
            tool_version.deprecated_at = datetime.now(timezone.utc)

            if sunset_date:
                tool_version.sunset_at = sunset_date

            if migration_notes:
                tool_version.migration_notes = migration_notes

            self.logger.warning(
                "Tool version deprecated",
                tool_name=tool_name,
                version=version,
                sunset_date=sunset_date.isoformat() if sunset_date else None,
            )

    def get_version_info(self, tool_name: str, version: str) -> Optional[ToolVersion]:
        """Get version information for a tool.

        Args:
            tool_name: Name of the MCP tool
            version: Version to query

        Returns:
            ToolVersion object or None if not found
        """
        return self.tools.get(tool_name, {}).get(version)

    def get_current_version(self, tool_name: str) -> Optional[str]:
        """Get the current version of a tool.

        Args:
            tool_name: Name of the MCP tool

        Returns:
            Current version string or None if not found
        """
        if tool_name not in self.tools:
            return None

        for version, version_info in self.tools[tool_name].items():
            if version_info.status == VersionStatus.CURRENT:
                return version

        return None

    def get_supported_versions(self, tool_name: str) -> List[str]:
        """Get all supported versions of a tool.

        Args:
            tool_name: Name of the MCP tool

        Returns:
            List of supported version strings
        """
        if tool_name not in self.tools:
            return []

        supported_versions = []
        for version, version_info in self.tools[tool_name].items():
            if version_info.status in [VersionStatus.CURRENT, VersionStatus.SUPPORTED]:
                supported_versions.append(version)

        return sorted(supported_versions, reverse=True)  # Newest first

    def is_version_supported(self, tool_name: str, version: str) -> bool:
        """Check if a tool version is supported.

        Args:
            tool_name: Name of the MCP tool
            version: Version to check

        Returns:
            True if version is supported
        """
        version_info = self.get_version_info(tool_name, version)
        if not version_info:
            return False

        return version_info.status in [VersionStatus.CURRENT, VersionStatus.SUPPORTED]

    def get_deprecation_info(
        self, tool_name: str, version: str
    ) -> Optional[Dict[str, Any]]:
        """Get deprecation information for a tool version.

        Args:
            tool_name: Name of the MCP tool
            version: Version to check

        Returns:
            Deprecation information or None
        """
        version_info = self.get_version_info(tool_name, version)
        if not version_info or version_info.status != VersionStatus.DEPRECATED:
            return None

        return {
            "deprecated_at": (
                version_info.deprecated_at.isoformat()
                if version_info.deprecated_at
                else None
            ),
            "sunset_at": (
                version_info.sunset_at.isoformat() if version_info.sunset_at else None
            ),
            "migration_notes": version_info.migration_notes,
            "current_version": self.get_current_version(tool_name),
        }

    def get_all_tools_info(self) -> Dict[str, Any]:
        """Get complete version information for all tools.

        Returns:
            Dictionary with all tools and their versions
        """
        tools_info = {}

        for tool_name, versions in self.tools.items():
            tools_info[tool_name] = {
                "current_version": self.get_current_version(tool_name),
                "supported_versions": self.get_supported_versions(tool_name),
                "versions": {
                    version: {
                        "status": version_info.status.value,
                        "introduced_at": version_info.introduced_at.isoformat(),
                        "deprecated_at": (
                            version_info.deprecated_at.isoformat()
                            if version_info.deprecated_at
                            else None
                        ),
                        "sunset_at": (
                            version_info.sunset_at.isoformat()
                            if version_info.sunset_at
                            else None
                        ),
                        "breaking_changes": version_info.breaking_changes,
                        "migration_notes": version_info.migration_notes,
                        "changelog": version_info.changelog,
                    }
                    for version, version_info in versions.items()
                },
            }

        return tools_info


# Global version registry instance
version_registry = ToolVersionRegistry()


def versioned_tool(
    version: str,
    tool_name: Optional[str] = None,
    status: VersionStatus = VersionStatus.CURRENT,
    breaking_changes: Optional[List[str]] = None,
    migration_notes: Optional[str] = None,
    changelog: Optional[List[str]] = None,
) -> Callable:
    """Decorator to add versioning support to MCP tools.

    Args:
        version: Semantic version string
        tool_name: Name of the tool (auto-detected if not provided)
        status: Version status
        breaking_changes: List of breaking changes
        migration_notes: Migration guidance
        changelog: List of changes in this version

    Returns:
        Decorated function with version support
    """

    def decorator(func: Callable) -> Callable:
        func_tool_name = tool_name or func.__name__

        # Register the version
        version_registry.register_version(
            tool_name=func_tool_name,
            version=version,
            status=status,
            breaking_changes=breaking_changes,
            migration_notes=migration_notes,
            changelog=changelog,
        )

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check if client requested specific version
            requested_version = kwargs.pop("_tool_version", None)

            if requested_version:
                # Validate requested version
                if not version_registry.is_version_supported(
                    func_tool_name, requested_version
                ):
                    return {
                        "status": "error",
                        "error": f"Unsupported tool version: {requested_version}",
                        "error_code": "UNSUPPORTED_VERSION",
                        "supported_versions": version_registry.get_supported_versions(
                            func_tool_name
                        ),
                        "current_version": version_registry.get_current_version(
                            func_tool_name
                        ),
                    }

                # Check for deprecation warnings
                version_info = version_registry.get_version_info(
                    func_tool_name, requested_version
                )
                if version_info and version_info.status == VersionStatus.DEPRECATED:
                    deprecation_info = version_registry.get_deprecation_info(
                        func_tool_name, requested_version
                    )
                    logger.warning(
                        "Using deprecated tool version",
                        tool_name=func_tool_name,
                        version=requested_version,
                        **deprecation_info if deprecation_info else {},
                    )

                    # Add deprecation warning to response
                    result = await func(*args, **kwargs)
                    if isinstance(result, dict):
                        result["version_warning"] = {
                            "type": "deprecation",
                            "message": f"Tool version {requested_version} is deprecated",
                            "deprecation_info": deprecation_info,
                        }
                    return result

            # Execute the tool function
            result = await func(*args, **kwargs)

            # Add version information to response
            if isinstance(result, dict):
                result["tool_version"] = {
                    "current": version,
                    "requested": requested_version or version,
                    "supported_versions": version_registry.get_supported_versions(
                        func_tool_name
                    ),
                }

            return result

        # Add version metadata to function
        wrapper._tool_version = version  # type: ignore[attr-defined]
        wrapper._tool_name = func_tool_name  # type: ignore[attr-defined]
        wrapper._version_info = version_registry.get_version_info(  # type: ignore[attr-defined]
            func_tool_name, version
        )

        return wrapper

    return decorator


def check_version_compatibility(
    tool_name: str,
    client_version: Optional[str] = None,
    min_version: Optional[str] = None,
    max_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Check version compatibility for a tool.

    Args:
        tool_name: Name of the MCP tool
        client_version: Version requested by client
        min_version: Minimum supported version
        max_version: Maximum supported version

    Returns:
        Compatibility check results
    """
    current_version = version_registry.get_current_version(tool_name)
    supported_versions = version_registry.get_supported_versions(tool_name)

    result: Dict[str, Any] = {
        "compatible": True,
        "tool_name": tool_name,
        "current_version": current_version,
        "supported_versions": supported_versions,
        "warnings": [],
        "errors": [],
    }

    if client_version:
        if not version_registry.is_version_supported(tool_name, client_version):
            result["compatible"] = False
            result["errors"].append(f"Unsupported version: {client_version}")
        else:
            deprecation_info = version_registry.get_deprecation_info(
                tool_name, client_version
            )
            if deprecation_info:
                result["warnings"].append(f"Version {client_version} is deprecated")
                result["deprecation_info"] = deprecation_info

    return result


def get_version_migration_guide(
    tool_name: str,
    from_version: str,
    to_version: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get migration guide for upgrading tool versions.

    Args:
        tool_name: Name of the MCP tool
        from_version: Current version
        to_version: Target version (current if not specified)

    Returns:
        Migration guide or None if not available
    """
    target_version = to_version or version_registry.get_current_version(tool_name)
    if not target_version:
        return None

    from_info = version_registry.get_version_info(tool_name, from_version)
    to_info = version_registry.get_version_info(tool_name, target_version)

    if not from_info or not to_info:
        return None

    return {
        "tool_name": tool_name,
        "from_version": from_version,
        "to_version": target_version,
        "breaking_changes": to_info.breaking_changes,
        "migration_notes": to_info.migration_notes,
        "changelog": to_info.changelog,
        "upgrade_recommended": from_info.status == VersionStatus.DEPRECATED,
    }


# Initialize default versions for all MCP tools
def initialize_default_versions() -> None:
    """Initialize default versions for all MCP tools."""
    tools_versions = {
        "scan_recommendations": {
            "version": "1.0.0",
            "changelog": [
                "Initial implementation with krr integration",
                "Support for all krr strategies (simple, medium, aggressive)",
                "Namespace filtering and resource pattern matching",
                "Comprehensive error handling and caching",
            ],
        },
        "preview_changes": {
            "version": "1.0.0",
            "changelog": [
                "Initial implementation with safety assessment",
                "Impact analysis and change preview",
                "Integration with safety validator",
                "Risk level calculation and warnings",
            ],
        },
        "request_confirmation": {
            "version": "1.0.0",
            "changelog": [
                "Initial implementation with token-based security",
                "Human-readable confirmation prompts",
                "Safety assessment integration",
                "Complete audit trail support",
            ],
        },
        "apply_recommendations": {
            "version": "1.0.0",
            "changelog": [
                "Initial implementation with kubectl integration",
                "Transaction-based execution with rollback support",
                "Progress tracking and real-time callbacks",
                "Comprehensive error handling and recovery",
            ],
        },
        "rollback_changes": {
            "version": "1.0.0",
            "changelog": [
                "Initial implementation with snapshot restoration",
                "Confirmation requirement for safety",
                "Complete audit trail integration",
                "Automatic cleanup of expired snapshots",
            ],
        },
        "get_safety_report": {
            "version": "1.0.0",
            "changelog": [
                "Initial implementation with comprehensive safety analysis",
                "Multi-factor risk assessment",
                "Production namespace protection",
                "Critical workload detection",
            ],
        },
        "get_execution_history": {
            "version": "1.0.0",
            "changelog": [
                "Initial implementation with audit trail querying",
                "Filtering by operation type and status",
                "Pagination and limit support",
                "Export capabilities for compliance",
            ],
        },
    }

    for tool_name, tool_info in tools_versions.items():
        version_registry.register_version(
            tool_name=tool_name,
            version=str(tool_info["version"]),
            status=VersionStatus.CURRENT,
            changelog=list(tool_info["changelog"]),
        )

    logger.info(
        "Initialized default tool versions",
        tools_count=len(tools_versions),
    )


# Initialize versions when module is imported
initialize_default_versions()
