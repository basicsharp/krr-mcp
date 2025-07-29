# CLAUDE.md - AI Assistant Guidelines for krr MCP Server Project

## Project Overview

You are helping to build the krr MCP Server, a safety-critical integration that bridges AI assistants with Kubernetes resource optimization. This server enables AI-powered analysis and application of resource recommendations while maintaining strict human oversight.

### Core Principle: Safety First
**CRITICAL**: No Kubernetes resources should ever be modified without explicit user confirmation. This is the #1 priority throughout the entire project.

## Project Context

### What is krr?
- Kubernetes Resource Recommender (krr) is a CLI tool that analyzes Prometheus metrics to recommend optimal CPU/memory settings
- Developed by Robusta, it can reduce cloud costs by up to 69% through intelligent right-sizing
- Works with existing Prometheus installations without requiring cluster agents

### What is MCP?
- Model Context Protocol enables AI assistants to interact with external tools
- FastMCP is the Python framework we're using to implement the server
- The server acts as a secure bridge between AI assistants and krr functionality

### Project Goals
1. Enable AI assistants to safely analyze Kubernetes resource usage
2. Generate and present optimization recommendations through natural language
3. Implement foolproof confirmation workflows before any changes
4. Maintain complete audit trails of all operations
5. Provide rollback capabilities for all modifications

## Development Guidelines

### Code Organization
```
krr-mcp-server/
├── src/
│   ├── server.py          # MCP server implementation
│   ├── safety/            # Confirmation and validation logic
│   ├── recommender/       # krr CLI integration
│   └── executor/          # kubectl execution with rollback
├── tests/                 # Comprehensive test suite
├── docs/                  # User and developer documentation
└── configs/              # Configuration templates
```

### Key Implementation Principles

#### 1. Async-First Design
- Use async/await throughout for non-blocking operations
- FastMCP provides async MCP protocol handling
- subprocess operations (krr, kubectl) must be async

#### 2. Fail-Safe Defaults
- Default to dry-run mode for all operations
- Require explicit confirmation for any cluster modifications
- Implement timeout handling for all external calls
- Always prepare rollback before applying changes

#### 3. Comprehensive Error Handling
```python
# Example pattern for all external operations
try:
    result = await run_krr_command(args)
except KrrNotFoundError:
    # User-friendly error about krr installation
except KubernetesAuthError:
    # Guide user to check kubeconfig
except PrometheusConnectionError:
    # Suggest checking Prometheus endpoint
except Exception as e:
    # Log full error, return safe user message
    logger.exception("Unexpected error in krr execution")
    return SafeError("An unexpected error occurred. Please check logs.")
```

#### 4. Structured Logging
- Use structlog for JSON-formatted logs
- Include context in every log entry (user, operation, cluster)
- Separate audit logs for all confirmation decisions
- Never log sensitive data (tokens, secrets)

### Safety Module Requirements

The safety module is the most critical component. It must:

1. **Intercept all execution requests**
   - No direct path from recommendation to execution
   - All changes must pass through safety validation

2. **Generate clear confirmation prompts**
   ```
   RESOURCE OPTIMIZATION CONFIRMATION
   
   The following changes will be applied to cluster 'production':
   
   Deployment: web-app (namespace: default)
   - CPU Request: 100m → 250m (+150%)
   - Memory Request: 128Mi → 256Mi (+100%)
   
   Impact Analysis:
   - Pods affected: 3
   - Potential restart required: Yes
   - Estimated monthly cost change: +$45
   
   Do you want to proceed? (type 'yes' to confirm):
   ```

3. **Validate all changes**
   - Prevent extreme resource changes (>500% increase)
   - Check against namespace policies
   - Verify cluster has sufficient capacity

4. **Maintain audit trail**
   ```python
   audit_entry = {
       "timestamp": datetime.utcnow(),
       "user": context.user,
       "action": "apply_recommendations",
       "changes": detailed_changes,
       "confirmation": user_response,
       "result": execution_result
   }
   ```

### MCP Tool Implementations

#### 1. scan_recommendations
- Purpose: Get krr recommendations for specified resources
- Safety: Read-only operation, no confirmation needed
- Key validations: Namespace exists, Prometheus accessible

#### 2. preview_changes
- Purpose: Show what would change without applying
- Safety: Runs kubectl dry-run to validate changes
- Returns: Detailed diff of current vs proposed

#### 3. request_confirmation
- Purpose: Present changes and get user approval
- Safety: Generates unique confirmation token
- Critical: Token expires after 5 minutes

#### 4. apply_recommendations
- Purpose: Execute approved changes
- Safety: Requires valid confirmation token
- Process:
  1. Validate token hasn't expired
  2. Capture current state for rollback
  3. Apply changes with kubectl
  4. Verify changes were applied
  5. Store rollback information

#### 5. rollback_changes
- Purpose: Revert to previous state
- Safety: Requires confirmation even for rollback
- Maintains history of all rollbacks

### Testing Requirements

#### Critical Test Scenarios
1. **Confirmation bypass attempts**
   - Test direct execution without confirmation
   - Test expired confirmation tokens
   - Test modified confirmation data

2. **Partial failure handling**
   - Some resources update successfully, others fail
   - Network interruption during execution
   - Kubernetes API errors mid-operation

3. **Edge cases**
   - Empty recommendations
   - Massive resource changes
   - Invalid resource specifications
   - Concurrent modification attempts

#### Test Coverage Goals
- Safety module: 100% coverage required
- Confirmation workflows: 100% coverage required
- Core MCP handlers: 95% minimum
- Overall project: 90% minimum

### Integration with Claude

When working on this project:

1. **Always consider safety implications**
   - "What could go wrong with this code?"
   - "How could a user accidentally cause damage?"
   - "What safeguards are missing?"

2. **Write defensive code**
   - Validate all inputs thoroughly
   - Never trust external data
   - Fail gracefully with helpful errors

3. **Document safety features**
   - Every safety check needs a comment explaining why
   - Document the confirmation flow clearly
   - Explain rollback procedures in detail

4. **Test safety scenarios first**
   - Write tests for dangerous operations before implementing
   - Test the "unhappy path" thoroughly
   - Verify confirmation can't be bypassed

### Common Pitfalls to Avoid

1. **Don't cache confirmation decisions**
   - Each operation needs fresh confirmation
   - Tokens must be single-use

2. **Don't trust krr output blindly**
   - Validate JSON structure
   - Sanity check recommendations
   - Handle malformed output gracefully

3. **Don't apply changes without verification**
   - Always verify current state first
   - Check if resources still exist
   - Confirm cluster connectivity

4. **Don't forget about RBAC**
   - Server needs appropriate permissions
   - Handle permission errors gracefully
   - Document required roles clearly

### Code Quality Standards

1. **Type hints everywhere**
   ```python
   async def apply_changes(
       recommendations: List[Recommendation],
       confirmation_token: str,
       dry_run: bool = True
   ) -> ExecutionResult:
   ```

2. **Docstrings for all public methods**
   ```python
   """Apply resource recommendations to the cluster.
   
   Args:
       recommendations: List of krr recommendations to apply
       confirmation_token: Valid confirmation token from request_confirmation
       dry_run: If True, simulate changes without applying
       
   Returns:
       ExecutionResult with status and details
       
   Raises:
       InvalidTokenError: If confirmation token is invalid/expired
       KubernetesError: If cluster operations fail
   """
   ```

3. **Constants for magic values**
   ```python
   CONFIRMATION_TIMEOUT_SECONDS = 300  # 5 minutes
   MAX_RESOURCE_CHANGE_PERCENT = 500  # 500% max increase
   DEFAULT_ROLLBACK_RETENTION_DAYS = 7
   ```

### Development Workflow

1. **Start with tests**
   - Write test for the feature/fix first
   - Ensure test fails appropriately
   - Implement minimum code to pass test

2. **Review safety implications**
   - Before committing, review all changes for safety
   - Ask: "Could this change lead to accidental resource modification?"
   - Add safety tests if new execution paths are created

3. **Update documentation**
   - Every new feature needs user documentation
   - Safety features need extra documentation
   - Include examples of safe usage

### Priority Order for Implementation

Based on TASKS.md milestones, focus on:

1. **Milestones 1-4 first** (Foundation and Safety)
   - These are the critical path
   - Safety module must be bulletproof before proceeding

2. **Comprehensive testing** (Milestone 7)
   - Don't skip tests for safety features
   - Integration tests are crucial for this project

3. **Documentation** (Milestone 8)
   - Users must understand safety features
   - Clear examples prevent accidents

### Questions to Ask During Development

1. "What's the worst thing that could happen if this code has a bug?"
2. "How can I make this fail safely?"
3. "Is the error message helpful enough for users to fix the issue?"
4. "Have I tested what happens when external tools (krr/kubectl) fail?"
5. "Is the confirmation prompt clear about what will change?"

### Remember

This project has the potential to modify production Kubernetes clusters. A bug could cause service outages, data loss, or significant cloud cost increases. Every line of code should be written with this responsibility in mind.

The goal is to make AI-assisted Kubernetes optimization both powerful AND safe. We're not just building features - we're building trust.

## Session Guidelines

When starting a new Claude Code session:

1. **Review current progress**: Check which milestones/tasks are completed
2. **Focus on one milestone**: Don't jump between major features
3. **Test as you go**: Run tests frequently, especially for safety features
4. **Commit meaningful chunks**: Each commit should be a working state
5. **Document decisions**: If you make architectural choices, document why

Always read PLANNING.md at the start of every new conversation, check TASKS.md before starting your work, mark completed tasks to TASKS.md immediately, and add newly discovered tasks to TASKS.md when found.

Your primary objective is to build a server that makes it impossible for users to accidentally damage their clusters while still providing powerful optimization capabilities.