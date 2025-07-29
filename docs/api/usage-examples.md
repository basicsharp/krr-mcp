# krr MCP Server Usage Examples

## Complete workflow for optimizing Kubernetes resources

### Step 1: Scan for recommendations

**Tool:** `scan_recommendations`

Get recommendations for production namespace

```json
{
  "namespace": "production",
  "strategy": "simple"
}
```

### Step 2: Preview changes

**Tool:** `preview_changes`

Preview what changes would be made

```json
{
  "recommendations": "[recommendations from step 1]"
}
```

### Step 3: Request confirmation

**Tool:** `request_confirmation`

Get user confirmation for changes

```json
{
  "changes": "[changes from step 2]",
  "risk_level": "medium"
}
```

### Step 4: Apply changes

**Tool:** `apply_recommendations`

Apply the approved changes

```json
{
  "confirmation_token": "[token from step 3]",
  "dry_run": false
}
```

## Examples of safety features in action

### High-risk changes

When requesting confirmation for high-impact changes

**Tool:** `request_confirmation`

**Safety Response:** Enhanced warnings and gradual rollout recommendations

### Production protection

Special handling for production namespaces

**Tool:** `preview_changes`

**Safety Response:** Production namespace warnings and extra validation

### Rollback recovery

Rolling back changes if something goes wrong

**Tool:** `rollback_changes`

**Safety Response:** Restore original resource configurations

