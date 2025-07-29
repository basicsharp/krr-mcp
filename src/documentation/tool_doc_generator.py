"""Tool documentation generator for MCP tools.

This module provides automatic generation of API reference documentation
for all MCP tools, including parameters, return values, examples, and usage.
"""

import inspect
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import structlog

logger = structlog.get_logger(__name__)


class ToolDocumentationGenerator:
    """Generate comprehensive documentation for MCP tools."""
    
    def __init__(self, server_instance, output_dir: Optional[Path] = None):
        """Initialize the documentation generator.
        
        Args:
            server_instance: KrrMCPServer instance to document
            output_dir: Directory to write documentation files
        """
        self.server = server_instance
        self.output_dir = output_dir or Path("docs/api")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    def generate_full_documentation(self) -> Dict[str, Any]:
        """Generate complete documentation for all MCP tools.
        
        Returns:
            Dictionary containing all documentation data
        """
        self.logger.info("Generating full MCP tools documentation")
        
        # Get all registered tools from the MCP server
        tools_info = self._extract_tools_info()
        
        # Generate documentation structure
        documentation = {
            "metadata": {
                "server_name": "krr-mcp-server",
                "version": "1.0.0",
                "generated_at": datetime.now().isoformat(),
                "description": "MCP server for safe Kubernetes resource optimization using krr",
                "safety_notice": (
                    "CRITICAL: This server implements comprehensive safety controls. "
                    "No Kubernetes resources are modified without explicit user confirmation."
                ),
            },
            "tools": tools_info,
            "safety_features": self._generate_safety_documentation(),
            "examples": self._generate_usage_examples(),
            "error_codes": self._generate_error_codes_documentation(),
        }
        
        # Write documentation files
        self._write_markdown_documentation(documentation)
        self._write_json_documentation(documentation)
        self._write_openapi_specification(documentation)
        
        self.logger.info(
            "Documentation generation completed",
            tools_count=len(tools_info),
            output_dir=str(self.output_dir),
        )
        
        return documentation
    
    def _extract_tools_info(self) -> Dict[str, Any]:
        """Extract information about all registered MCP tools."""
        tools_info = {}
        
        # Get tools from the FastMCP server instance
        # Note: This is a simplified approach - in a real implementation,
        # you'd need to access the actual registered tools from FastMCP
        
        tool_definitions = {
            "scan_recommendations": {
                "description": "Scan Kubernetes cluster for resource optimization recommendations",
                "parameters": {
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace to analyze (optional, all if not specified)",
                        "required": False,
                    },
                    "strategy": {
                        "type": "string",
                        "description": "krr strategy to use (simple, medium, aggressive)",
                        "required": False,
                        "enum": ["simple", "medium", "aggressive"],
                    },
                    "resource_filter": {
                        "type": "string", 
                        "description": "Filter resources by name pattern (optional)",
                        "required": False,
                    },
                },
                "returns": {
                    "type": "object",
                    "description": "Dictionary with recommendations and metadata",
                    "properties": {
                        "status": {"type": "string", "enum": ["success", "error"]},
                        "recommendations": {"type": "array", "description": "List of optimization recommendations"},
                        "metadata": {"type": "object", "description": "Scan metadata and statistics"},
                        "summary": {"type": "object", "description": "Summary of potential savings"},
                    },
                },
                "safety_level": "read_only",
                "examples": [
                    {
                        "description": "Scan all namespaces with simple strategy",
                        "input": {"strategy": "simple"},
                        "output_sample": {
                            "status": "success",
                            "recommendations": [
                                {
                                    "object": {"kind": "Deployment", "name": "web-app", "namespace": "default"},
                                    "current": {"requests": {"cpu": "100m", "memory": "128Mi"}},
                                    "recommended": {"requests": {"cpu": "250m", "memory": "256Mi"}},
                                }
                            ],
                        },
                    }
                ],
            },
            "preview_changes": {
                "description": "Preview what changes would be made without applying them",
                "parameters": {
                    "recommendations": {
                        "type": "array",
                        "description": "List of recommendations to preview",
                        "required": True,
                    },
                },
                "returns": {
                    "type": "object",
                    "description": "Dictionary with change preview and impact analysis",
                    "properties": {
                        "status": {"type": "string", "enum": ["success", "error"]},
                        "preview": {"type": "object", "description": "Detailed change preview"},
                        "next_steps": {"type": "array", "description": "Recommended next steps"},
                    },
                },
                "safety_level": "analysis_only",
            },
            "request_confirmation": {
                "description": "Request user confirmation for proposed changes",
                "parameters": {
                    "changes": {
                        "type": "object",
                        "description": "Detailed description of proposed changes",
                        "required": True,
                    },
                    "risk_level": {
                        "type": "string",
                        "description": "Risk level (low, medium, high, critical)",
                        "required": False,
                        "default": "medium",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                },
                "returns": {
                    "type": "object",
                    "description": "Dictionary with confirmation prompt and token",
                    "properties": {
                        "status": {"type": "string", "enum": ["success", "error"]},
                        "confirmation_required": {"type": "boolean"},
                        "confirmation_token": {"type": "string", "description": "Token for applying changes"},
                        "confirmation_prompt": {"type": "string", "description": "Human-readable confirmation prompt"},
                        "safety_assessment": {"type": "object", "description": "Risk assessment details"},
                    },
                },
                "safety_level": "confirmation_required",
                "critical_notice": "SAFETY CRITICAL: This tool must be called before any cluster modifications.",
            },
            "apply_recommendations": {
                "description": "Apply approved recommendations to the cluster",
                "parameters": {
                    "confirmation_token": {
                        "type": "string",
                        "description": "Valid confirmation token from user approval",
                        "required": True,
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If True, simulate changes without applying them",
                        "required": False,
                        "default": False,
                    },
                },
                "returns": {
                    "type": "object",
                    "description": "Dictionary with execution results and rollback information",
                    "properties": {
                        "status": {"type": "string", "enum": ["success", "error"]},
                        "transaction_id": {"type": "string"},
                        "execution_status": {"type": "string"},
                        "rollback_available": {"type": "boolean"},
                        "audit_entry_id": {"type": "string"},
                    },
                },
                "safety_level": "cluster_modification",
                "critical_notice": "SAFETY CRITICAL: This tool modifies cluster resources and must only be called with a valid confirmation token.",
            },
            "rollback_changes": {
                "description": "Rollback previously applied changes",
                "parameters": {
                    "rollback_id": {
                        "type": "string",
                        "description": "ID of the changes to rollback (rollback_snapshot_id)",
                        "required": True,
                    },
                    "confirmation_token": {
                        "type": "string",
                        "description": "Valid confirmation token for rollback",
                        "required": True,
                    },
                },
                "returns": {
                    "type": "object",
                    "description": "Dictionary with rollback results",
                    "properties": {
                        "status": {"type": "string", "enum": ["success", "error"]},
                        "rollback_id": {"type": "string"},
                        "rolled_back": {"type": "boolean"},
                        "affected_resources": {"type": "array"},
                        "audit_entry_id": {"type": "string"},
                    },
                },
                "safety_level": "cluster_modification",
                "critical_notice": "SAFETY CRITICAL: This tool modifies cluster resources to restore previous state. Requires confirmation even for rollback operations.",
            },
            "get_safety_report": {
                "description": "Generate safety assessment report for proposed changes",
                "parameters": {
                    "changes": {
                        "type": "object",
                        "description": "Proposed changes to analyze",
                        "required": True,
                    },
                },
                "returns": {
                    "type": "object",
                    "description": "Dictionary with comprehensive safety report",
                    "properties": {
                        "status": {"type": "string", "enum": ["success", "error"]},
                        "safety_report": {"type": "object", "description": "Detailed safety assessment"},
                    },
                },
                "safety_level": "analysis_only",
            },
            "get_execution_history": {
                "description": "Get history of previous executions and their status",
                "parameters": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of history entries to return",
                        "required": False,
                        "default": 10,
                    },
                    "operation_filter": {
                        "type": "string",
                        "description": "Filter by operation type (optional)",
                        "required": False,
                    },
                    "status_filter": {
                        "type": "string",
                        "description": "Filter by status (optional)",
                        "required": False,
                    },
                },
                "returns": {
                    "type": "object",
                    "description": "Dictionary with execution history",
                    "properties": {
                        "status": {"type": "string", "enum": ["success", "error"]},
                        "history": {"type": "array", "description": "List of historical executions"},
                        "total_count": {"type": "integer"},
                        "filters_applied": {"type": "object"},
                    },
                },
                "safety_level": "read_only",
            },
        }
        
        return tool_definitions
    
    def _generate_safety_documentation(self) -> Dict[str, Any]:
        """Generate documentation for safety features."""
        return {
            "overview": (
                "The krr MCP Server implements comprehensive safety controls to prevent "
                "accidental cluster damage while enabling AI-assisted optimization."
            ),
            "safety_levels": {
                "read_only": {
                    "description": "Tools that only read cluster data without making changes",
                    "tools": ["scan_recommendations", "get_execution_history"],
                    "risk": "None - Safe to execute without confirmation",
                },
                "analysis_only": {
                    "description": "Tools that analyze and preview changes without applying them",
                    "tools": ["preview_changes", "get_safety_report"],
                    "risk": "None - No cluster modifications performed",
                },
                "confirmation_required": {
                    "description": "Tools that require user confirmation before proceeding",
                    "tools": ["request_confirmation"],
                    "risk": "Low - Generates confirmation tokens but makes no changes",
                },
                "cluster_modification": {
                    "description": "Tools that modify cluster resources",
                    "tools": ["apply_recommendations", "rollback_changes"],
                    "risk": "High - Requires valid confirmation token and creates audit trail",
                },
            },
            "safety_guarantees": [
                "No recommendations applied without explicit user confirmation",
                "Complete audit trail for all operations",
                "Rollback capability for all modifications",
                "Token-based security prevents replay attacks",
                "Multi-layer validation prevents dangerous operations",
                "Production namespace protection with enhanced warnings",
                "Automatic resource limit validation",
                "Critical workload detection and special handling",
            ],
            "confirmation_workflow": {
                "description": "All cluster modifications require a multi-step confirmation process",
                "steps": [
                    "1. Generate recommendations using scan_recommendations",
                    "2. Preview changes using preview_changes (optional but recommended)",
                    "3. Request confirmation using request_confirmation",
                    "4. Review confirmation prompt and safety assessment",
                    "5. Apply changes using apply_recommendations with confirmation token",
                    "6. Monitor results and use rollback_changes if needed",
                ],
            },
        }
    
    def _generate_usage_examples(self) -> Dict[str, Any]:
        """Generate comprehensive usage examples."""
        return {
            "basic_workflow": {
                "description": "Complete workflow for optimizing Kubernetes resources",
                "steps": [
                    {
                        "step": 1,
                        "action": "Scan for recommendations",
                        "tool": "scan_recommendations",
                        "example": {
                            "input": {"namespace": "production", "strategy": "simple"},
                            "description": "Get recommendations for production namespace",
                        },
                    },
                    {
                        "step": 2,
                        "action": "Preview changes",
                        "tool": "preview_changes",
                        "example": {
                            "input": {"recommendations": "[recommendations from step 1]"},
                            "description": "Preview what changes would be made",
                        },
                    },
                    {
                        "step": 3,
                        "action": "Request confirmation",
                        "tool": "request_confirmation",
                        "example": {
                            "input": {"changes": "[changes from step 2]", "risk_level": "medium"},
                            "description": "Get user confirmation for changes",
                        },
                    },
                    {
                        "step": 4,
                        "action": "Apply changes",
                        "tool": "apply_recommendations",
                        "example": {
                            "input": {"confirmation_token": "[token from step 3]", "dry_run": False},
                            "description": "Apply the approved changes",
                        },
                    },
                ],
            },
            "safety_scenarios": {
                "description": "Examples of safety features in action",
                "scenarios": [
                    {
                        "scenario": "High-risk changes",
                        "description": "When requesting confirmation for high-impact changes",
                        "example": {
                            "tool": "request_confirmation",
                            "input": {"changes": "[large resource increases]", "risk_level": "high"},
                            "safety_response": "Enhanced warnings and gradual rollout recommendations",
                        },
                    },
                    {
                        "scenario": "Production protection",
                        "description": "Special handling for production namespaces",
                        "example": {
                            "tool": "preview_changes",
                            "input": {"recommendations": "[production namespace changes]"},
                            "safety_response": "Production namespace warnings and extra validation",
                        },
                    },
                    {
                        "scenario": "Rollback recovery",
                        "description": "Rolling back changes if something goes wrong",
                        "example": {
                            "tool": "rollback_changes",
                            "input": {"rollback_id": "[snapshot_id]", "confirmation_token": "[new_token]"},
                            "safety_response": "Restore original resource configurations",
                        },
                    },
                ],
            },
        }
    
    def _generate_error_codes_documentation(self) -> Dict[str, Any]:
        """Generate documentation for error codes."""
        return {
            "overview": "All MCP tools return structured error responses with specific error codes for programmatic handling",
            "error_codes": {
                "COMPONENT_NOT_READY": {
                    "description": "Required server components not initialized",
                    "resolution": "Wait for server initialization to complete",
                    "tools": ["scan_recommendations", "preview_changes", "request_confirmation"],
                },
                "INVALID_STRATEGY": {
                    "description": "Invalid krr strategy provided",
                    "resolution": "Use one of: simple, medium, aggressive",
                    "tools": ["scan_recommendations"],
                },
                "SCAN_FAILED": {
                    "description": "krr scan operation failed",
                    "resolution": "Check cluster connectivity and krr installation",
                    "tools": ["scan_recommendations"],
                },
                "NO_VALID_RECOMMENDATIONS": {
                    "description": "No valid recommendations to process",
                    "resolution": "Verify recommendation format and content",
                    "tools": ["preview_changes", "request_confirmation"],
                },
                "INVALID_TOKEN": {
                    "description": "Invalid or expired confirmation token",
                    "resolution": "Request new confirmation token",
                    "tools": ["apply_recommendations", "rollback_changes"],
                },
                "EXECUTION_FAILED": {
                    "description": "Failed to execute kubectl commands",
                    "resolution": "Check cluster connectivity and permissions",
                    "tools": ["apply_recommendations"],
                },
                "ROLLBACK_NOT_FOUND": {
                    "description": "Rollback snapshot not found or expired",
                    "resolution": "Check rollback ID and retention policies",
                    "tools": ["rollback_changes"],
                },
            },
            "error_handling_best_practices": [
                "Always check the 'status' field in responses",
                "Use 'error_code' field for programmatic error handling",
                "Display 'error' field message to users",
                "Implement retry logic for transient errors",
                "Log errors for troubleshooting and monitoring",
            ],
        }
    
    def _write_markdown_documentation(self, documentation: Dict[str, Any]) -> None:
        """Write documentation as Markdown files."""
        # Main API reference
        with open(self.output_dir / "api-reference.md", "w") as f:
            f.write(self._generate_markdown_content(documentation))
        
        # Safety guide
        with open(self.output_dir / "safety-guide.md", "w") as f:
            f.write(self._generate_safety_markdown(documentation["safety_features"]))
        
        # Usage examples
        with open(self.output_dir / "usage-examples.md", "w") as f:
            f.write(self._generate_examples_markdown(documentation["examples"]))
    
    def _write_json_documentation(self, documentation: Dict[str, Any]) -> None:
        """Write documentation as JSON for programmatic access."""
        with open(self.output_dir / "api-documentation.json", "w") as f:
            json.dump(documentation, f, indent=2, default=str)
    
    def _write_openapi_specification(self, documentation: Dict[str, Any]) -> None:
        """Write OpenAPI 3.0 specification."""
        openapi_spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "krr MCP Server API",
                "version": documentation["metadata"]["version"],
                "description": documentation["metadata"]["description"],
            },
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": {
                    "ConfirmationToken": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-Confirmation-Token",
                        "description": "Required for cluster modification operations",
                    }
                }
            },
        }
        
        # Convert tools to OpenAPI paths
        for tool_name, tool_info in documentation["tools"].items():
            openapi_spec["paths"][f"/tools/{tool_name}"] = {
                "post": {
                    "summary": tool_info["description"],
                    "parameters": self._convert_parameters_to_openapi(tool_info.get("parameters", {})),
                    "responses": {
                        "200": {
                            "description": "Successful response",
                            "content": {
                                "application/json": {
                                    "schema": tool_info.get("returns", {"type": "object"})
                                }
                            }
                        }
                    }
                }
            }
        
        with open(self.output_dir / "openapi.json", "w") as f:
            json.dump(openapi_spec, f, indent=2)
    
    def _generate_markdown_content(self, documentation: Dict[str, Any]) -> str:
        """Generate main Markdown documentation content."""
        content = f"""# krr MCP Server API Reference

Generated on: {documentation['metadata']['generated_at']}

{documentation['metadata']['description']}

## ⚠️ SAFETY NOTICE

{documentation['metadata']['safety_notice']}

## Available Tools

"""
        
        for tool_name, tool_info in documentation["tools"].items():
            content += f"### {tool_name}\n\n"
            content += f"{tool_info['description']}\n\n"
            
            if tool_info.get("critical_notice"):
                content += f"**{tool_info['critical_notice']}**\n\n"
            
            content += f"**Safety Level:** {tool_info.get('safety_level', 'unknown')}\n\n"
            
            # Parameters
            if tool_info.get("parameters"):
                content += "**Parameters:**\n\n"
                for param_name, param_info in tool_info["parameters"].items():
                    required = " (required)" if param_info.get("required") else " (optional)"
                    content += f"- `{param_name}` ({param_info['type']}){required}: {param_info['description']}\n"
                content += "\n"
            
            # Returns
            if tool_info.get("returns"):
                content += f"**Returns:** {tool_info['returns']['description']}\n\n"
            
            # Examples
            if tool_info.get("examples"):
                content += "**Examples:**\n\n"
                for example in tool_info["examples"]:
                    content += f"*{example['description']}*\n\n"
                    content += "```json\n"
                    content += json.dumps(example.get("input", {}), indent=2)
                    content += "\n```\n\n"
            
            content += "---\n\n"
        
        return content
    
    def _generate_safety_markdown(self, safety_features: Dict[str, Any]) -> str:
        """Generate safety guide Markdown content."""
        content = f"""# krr MCP Server Safety Guide

{safety_features['overview']}

## Safety Levels

"""
        
        for level, info in safety_features["safety_levels"].items():
            content += f"### {level.replace('_', ' ').title()}\n\n"
            content += f"{info['description']}\n\n"
            content += f"**Tools:** {', '.join(info['tools'])}\n\n"
            content += f"**Risk Level:** {info['risk']}\n\n"
        
        content += "## Safety Guarantees\n\n"
        for guarantee in safety_features["safety_guarantees"]:
            content += f"- {guarantee}\n"
        
        content += f"\n## Confirmation Workflow\n\n{safety_features['confirmation_workflow']['description']}\n\n"
        for step in safety_features["confirmation_workflow"]["steps"]:
            content += f"{step}\n"
        
        return content
    
    def _generate_examples_markdown(self, examples: Dict[str, Any]) -> str:
        """Generate usage examples Markdown content."""
        content = "# krr MCP Server Usage Examples\n\n"
        
        # Basic workflow
        workflow = examples["basic_workflow"]
        content += f"## {workflow['description']}\n\n"
        
        for step_info in workflow["steps"]:
            content += f"### Step {step_info['step']}: {step_info['action']}\n\n"
            content += f"**Tool:** `{step_info['tool']}`\n\n"
            content += f"{step_info['example']['description']}\n\n"
            content += "```json\n"
            content += json.dumps(step_info["example"]["input"], indent=2)
            content += "\n```\n\n"
        
        # Safety scenarios
        scenarios = examples["safety_scenarios"]
        content += f"## {scenarios['description']}\n\n"
        
        for scenario in scenarios["scenarios"]:
            content += f"### {scenario['scenario']}\n\n"
            content += f"{scenario['description']}\n\n"
            content += f"**Tool:** `{scenario['example']['tool']}`\n\n"
            content += f"**Safety Response:** {scenario['example']['safety_response']}\n\n"
        
        return content
    
    def _convert_parameters_to_openapi(self, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert parameter definitions to OpenAPI format."""
        openapi_params = []
        
        for param_name, param_info in parameters.items():
            openapi_param = {
                "name": param_name,
                "in": "query",
                "description": param_info["description"],
                "required": param_info.get("required", False),
                "schema": {"type": param_info["type"]},
            }
            
            if param_info.get("enum"):
                openapi_param["schema"]["enum"] = param_info["enum"]
            
            if param_info.get("default") is not None:
                openapi_param["schema"]["default"] = param_info["default"]
            
            openapi_params.append(openapi_param)
        
        return openapi_params