# krr MCP Server Safety Guide

The krr MCP Server implements comprehensive safety controls to prevent accidental cluster damage while enabling AI-assisted optimization.

## Safety Levels

### Read Only

Tools that only read cluster data without making changes

**Tools:** scan_recommendations, get_execution_history

**Risk Level:** None - Safe to execute without confirmation

### Analysis Only

Tools that analyze and preview changes without applying them

**Tools:** preview_changes, get_safety_report

**Risk Level:** None - No cluster modifications performed

### Confirmation Required

Tools that require user confirmation before proceeding

**Tools:** request_confirmation

**Risk Level:** Low - Generates confirmation tokens but makes no changes

### Cluster Modification

Tools that modify cluster resources

**Tools:** apply_recommendations, rollback_changes

**Risk Level:** High - Requires valid confirmation token and creates audit trail

## Safety Guarantees

- No recommendations applied without explicit user confirmation
- Complete audit trail for all operations
- Rollback capability for all modifications
- Token-based security prevents replay attacks
- Multi-layer validation prevents dangerous operations
- Production namespace protection with enhanced warnings
- Automatic resource limit validation
- Critical workload detection and special handling

## Confirmation Workflow

All cluster modifications require a multi-step confirmation process

1. Generate recommendations using scan_recommendations
2. Preview changes using preview_changes (optional but recommended)
3. Request confirmation using request_confirmation
4. Review confirmation prompt and safety assessment
5. Apply changes using apply_recommendations with confirmation token
6. Monitor results and use rollback_changes if needed
