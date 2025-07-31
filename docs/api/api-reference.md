# KRR MCP Server API Reference

Generated on: 2025-07-31T17:36:11.740343

MCP server for safe Kubernetes resource optimization using krr

## ⚠️ SAFETY NOTICE

CRITICAL: This server implements comprehensive safety controls. No Kubernetes resources are modified without explicit user confirmation.

## Available Tools

### scan_recommendations

Scan Kubernetes cluster for resource optimization recommendations

**Safety Level:** read_only

**Parameters:**

- `namespace` (string) (optional): Kubernetes namespace to analyze (optional, all if not specified)
- `strategy` (string) (optional): krr strategy to use (simple, medium, aggressive)
- `resource_filter` (string) (optional): Filter resources by name pattern (optional)

**Returns:** Dictionary with recommendations and metadata

**Examples:**

*Scan all namespaces with simple strategy*

```json
{
  "strategy": "simple"
}
```

---

### preview_changes

Preview what changes would be made without applying them

**Safety Level:** analysis_only

**Parameters:**

- `recommendations` (array) (required): List of recommendations to preview

**Returns:** Dictionary with change preview and impact analysis

---

### request_confirmation

Request user confirmation for proposed changes

**SAFETY CRITICAL: This tool must be called before any cluster modifications.**

**Safety Level:** confirmation_required

**Parameters:**

- `changes` (object) (required): Detailed description of proposed changes
- `risk_level` (string) (optional): Risk level (low, medium, high, critical)

**Returns:** Dictionary with confirmation prompt and token

---

### apply_recommendations

Apply approved recommendations to the cluster

**SAFETY CRITICAL: This tool modifies cluster resources and must only be called with a valid confirmation token.**

**Safety Level:** cluster_modification

**Parameters:**

- `confirmation_token` (string) (required): Valid confirmation token from user approval
- `dry_run` (boolean) (optional): If True, simulate changes without applying them

**Returns:** Dictionary with execution results and rollback information

---

### rollback_changes

Rollback previously applied changes

**SAFETY CRITICAL: This tool modifies cluster resources to restore previous state. Requires confirmation even for rollback operations.**

**Safety Level:** cluster_modification

**Parameters:**

- `rollback_id` (string) (required): ID of the changes to rollback (rollback_snapshot_id)
- `confirmation_token` (string) (required): Valid confirmation token for rollback

**Returns:** Dictionary with rollback results

---

### get_safety_report

Generate safety assessment report for proposed changes

**Safety Level:** analysis_only

**Parameters:**

- `changes` (object) (required): Proposed changes to analyze

**Returns:** Dictionary with comprehensive safety report

---

### get_execution_history

Get history of previous executions and their status

**Safety Level:** read_only

**Parameters:**

- `limit` (integer) (optional): Maximum number of history entries to return
- `operation_filter` (string) (optional): Filter by operation type (optional)
- `status_filter` (string) (optional): Filter by status (optional)

**Returns:** Dictionary with execution history

---
