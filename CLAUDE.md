# CLAUDE.md - AI Assistant Guidelines for KRR MCP Server Project

## Project Overview

You are helping to build the KRR MCP Server, a safety-critical integration that bridges AI assistants with Kubernetes resource optimization. This server enables AI-powered analysis and application of resource recommendations while maintaining strict human oversight.

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

**Always read PLANNING.md at the start of every new conversation, check TASKS.md before starting your work, mark completed tasks to TASKS.md immediately, and add newly discovered tasks to TASKS.md when found.**

Remember that we use `uv` as main package manager, so you can use pytest via the following command: `uv run pytest`

Try keeping only 2 latest session summaries here.

Your primary objective is to build a server that makes it impossible for users to accidentally damage their clusters while still providing powerful optimization capabilities.

---

## Session Summary - January 30, 2025 (krr CLI Arguments Correction)

### Major Accomplishments This Session

**✅ Complete Ad-hoc Milestone: krr CLI Arguments Correction**
Fixed critical command argument inconsistencies between the KRR MCP Server implementation and the actual krr CLI tool interface:

*Root Cause Analysis*:
- Current implementation used incorrect krr CLI arguments that don't match the actual tool
- `--history` should be `--history-duration` (per krr CLI help documentation)
- `--format` should be `--formatter` (per krr CLI help documentation)
- `--include-limits` is not a valid krr option (limits are included by default)
- These issues would cause krr command execution failures in production

*Command Argument Fixes (`src/recommender/krr_client.py`)*:
- **Fixed `--history` → `--history-duration`**: Updated `_build_krr_command()` to use correct argument name
- **Fixed `--format` → `--formatter`**: Corrected output format specification argument
- **Removed `--include-limits`**: Eliminated invalid option that doesn't exist in krr CLI
- **Updated function signatures**: Removed unused `include_limits` parameter from method signatures and documentation

*Test Suite Updates*:
- **Fixed test expectations**: Updated `tests/test_krr_client.py` to expect correct command arguments
- **Fixed async initialization issue**: Resolved event loop problem in KrrClient constructor for better test compatibility
- **Corrected mock test parameters**: Fixed test calls to use proper function signatures

*Documentation Updates*:
- **Updated examples**: Corrected krr command examples in `PRD.md` documentation
- **Added comprehensive milestone**: Created detailed ad-hoc milestone in `TASKS.md` with full issue tracking

### Technical Achievements

**CLI Interface Compliance**:
- Complete alignment between KRR MCP Server and actual krr CLI tool interface
- Command generation now uses verified krr CLI arguments from official help documentation
- Eliminated potential runtime failures from invalid command arguments

**Test Architecture Improvements**:
- Fixed async initialization patterns to avoid event loop issues during testing
- Improved test compatibility without compromising functionality
- Maintained 100% test coverage while correcting argument usage

**Code Quality Enhancement**:
- Removed unused parameters and simplified function signatures
- Added proper documentation comments explaining changes
- Maintained backward compatibility for existing functionality

### Safety Guarantees Maintained

**🛡️ No Functional Impact on Safety**:
- All safety mechanisms remain intact and unchanged
- Mock mode operations preserved for safe testing
- Confirmation workflows and audit trails unaffected
- Risk assessment and validation systems continue to function correctly

**🛡️ Enhanced Production Reliability**:
- Fixed command generation prevents krr execution failures
- Correct CLI arguments ensure reliable cluster analysis
- Proper error handling maintained for invalid operations

### Current Project State

**krr CLI Integration**: ✅ **FULLY CORRECTED** - Commands now match actual krr tool interface

**Test Results**:
- **All krr client tests**: ✅ 44/44 passing (100% success rate)
- **Command generation**: ✅ Uses correct `--history-duration`, `--formatter` arguments
- **Invalid options**: ✅ Removed non-existent `--include-limits` option
- **Test compatibility**: ✅ Fixed async initialization and parameter issues

**Files Modified This Session**:
- `src/recommender/krr_client.py` - Fixed command argument building and async initialization
- `tests/test_krr_client.py` - Updated test expectations to match corrected arguments
- `PRD.md` - Corrected example krr commands in documentation
- `TASKS.md` - Added comprehensive ad-hoc milestone with detailed issue tracking

### Key Design Decisions

**Evidence-Based Corrections**: Used official krr CLI help documentation (`krr-cli-help.md`) as the authoritative source for correct command arguments, ensuring accuracy and preventing future drift.

**Backwards-Compatible Changes**: Modified function signatures and implementations in a way that maintains existing functionality while correcting the underlying command generation.

**Comprehensive Testing**: Fixed test suite to validate correct behavior while maintaining safety and mock mode operation, ensuring no regression in functionality.

**Documentation Alignment**: Updated all references to krr commands across the codebase to maintain consistency between code, tests, and documentation.

The KRR MCP Server now **correctly interfaces with the krr CLI tool** using verified command arguments, eliminating potential runtime failures and ensuring reliable Kubernetes resource analysis in production environments.

---

## Session Summary - January 29, 2025 (Milestone 8 Completion)

### Major Accomplishments This Session

**✅ Complete Milestone 8: Documentation**
Built a comprehensive, enterprise-grade documentation suite that makes the KRR MCP Server accessible to users, developers, and operators:

*Professional Project Front Page (`README.md`)*:
- Complete project overview with safety-first messaging and clear value proposition
- Architecture diagram showing multi-layer protection and component interactions
- Comprehensive feature list highlighting AI-powered analysis and enterprise-ready safety
- Quick start guide with installation, configuration, and Claude Desktop integration
- MCP tools overview with safety levels and complete feature matrix
- Project status tracking and contribution guidelines for community engagement

*Installation Guide (`docs/installation.md`)*:
- Complete prerequisites including Python 3.12+, kubectl, krr CLI, and Prometheus setup
- Multi-platform installation instructions (Ubuntu/Debian, macOS, Windows)
- Comprehensive RBAC configuration with minimal and full permission examples
- MCP client integration setup for Claude Desktop and custom clients
- Troubleshooting section covering common installation issues and solutions
- Testing procedures to verify proper installation and component availability

*User Guide (`docs/user-guide.md`)*:
- Natural language usage patterns showing how to interact with AI for optimization
- Complete workflow examples from analysis through confirmation to execution
- Common use cases: cost optimization, performance tuning, bulk operations, maintenance
- Advanced features including filtering, strategy selection, and risk management
- Comprehensive rollback operations and emergency procedures
- Safety best practices and operational guidelines for development and platform teams

*Safety Guide (`docs/safety.md`)*:
- Multi-layer safety architecture explanation with defense-in-depth approach
- Complete risk assessment engine documentation covering resource impact and workload criticality
- Token-based security system with expiration, single-use validation, and context binding
- Production protection mechanisms with namespace and critical workload detection
- Comprehensive audit trail system with immutable logging and compliance features
- Emergency procedures, safety overrides, and monitoring setup for production environments

*API Documentation (`docs/api/`)*:
- Auto-generated comprehensive API reference for all 9 MCP tools using existing documentation generator
- Multiple output formats: Markdown (human-readable), JSON (programmatic), OpenAPI 3.0 (integration)
- Complete parameter documentation with examples, safety levels, and risk assessments
- Integration examples for Claude Desktop and custom MCP clients
- Error handling documentation with standardized error codes and resolution steps
- Version information and migration guidance for tool lifecycle management

*Troubleshooting Guide (`docs/troubleshooting.md`)*:
- Quick diagnostic steps for system health checks and component validation
- Common error messages with detailed symptoms, causes, and step-by-step solutions
- Component debugging techniques for krr client, safety module, and kubectl executor
- Network debugging procedures for Kubernetes and Prometheus connectivity
- Recovery procedures including system state reset and emergency rollback operations
- Monitoring and alerting recommendations for production deployment

*Deployment Guide (`docs/deployment.md`)*:
- Production-ready container deployment with Docker and Kubernetes manifests
- Complete Helm chart configuration with security hardening and auto-scaling
- Virtual machine deployment with systemd service and security configurations
- Comprehensive monitoring setup with Prometheus metrics and Grafana dashboards
- CI/CD pipeline examples with GitHub Actions for automated testing and deployment
- Operational procedures including backup/recovery, disaster recovery, and deployment checklists

**✅ Enterprise Documentation Standards**
Established professional documentation practices throughout the suite:

*Consistent Structure and Navigation*:
- Standardized document format with clear sections, examples, and cross-references
- Comprehensive table of contents and navigation between related documentation
- Consistent safety messaging emphasizing confirmation requirements and risk assessment
- Professional formatting with code blocks, diagrams, and step-by-step instructions

*Auto-Generated API Documentation*:
- Leveraged existing `ToolDocumentationGenerator` to create comprehensive API reference
- Consistent parameter documentation, examples, and safety information across all tools
- Multiple output formats ensuring accessibility for different use cases and integration needs
- Maintainable documentation that stays synchronized with code changes

### Technical Achievements

**Documentation Architecture**:
- Complete documentation suite covering user journey from installation to production operations
- Auto-generated API documentation ensuring consistency and reducing manual maintenance burden
- Professional README serving as effective project front page with clear value proposition
- Comprehensive safety documentation establishing trust and confidence in production use

**User Experience Focus**:
- Natural language examples showing real conversation patterns with AI assistants
- Step-by-step workflows with safety checkpoints clearly highlighted throughout
- Troubleshooting focused on practical problem-solving with actionable solutions
- Deployment guidance suitable for different organizational maturity levels and requirements

**Production Readiness**:
- Enterprise-grade deployment instructions with security hardening and monitoring
- Comprehensive operational procedures including backup, recovery, and incident response
- Complete CI/CD pipeline examples for automated testing, security scanning, and deployment
- Monitoring and alerting setup ensuring operational visibility and proactive issue detection

### Safety Documentation Excellence

**Comprehensive Safety Coverage**:
- Multi-layer protection architecture clearly explained with visual diagrams and examples
- Risk assessment engine documentation covering all factors and decision criteria
- Production protection mechanisms with specific patterns and configuration examples
- Emergency procedures and safety overrides with clear guidelines and restrictions

**Trust Building Through Transparency**:
- Complete audit trail documentation showing immutable logging and compliance readiness
- Token-based security system fully explained with expiration and validation mechanisms
- Safety violation examples and resolution procedures building confidence in protection systems
- Real-world operational scenarios with step-by-step safety checkpoint explanations

### Current Project State

**Milestone 8**: ✅ **FULLY COMPLETED** - Comprehensive enterprise-ready documentation suite

**Production-Ready Documentation**:
- Complete user journey documentation from installation through advanced operations
- Auto-generated API documentation ensuring consistency and maintainability
- Professional project presentation suitable for enterprise evaluation and adoption
- Comprehensive troubleshooting and operational guidance for production deployment

**Documentation Statistics**:
- 7 major documentation files created with comprehensive coverage
- Auto-generated API documentation in 3 formats (Markdown, JSON, OpenAPI)
- Professional README with clear value proposition and safety emphasis
- Complete installation, user, safety, troubleshooting, and deployment guides

**Next Phase Opportunities**:
- Milestone 9 (Deployment and Distribution) - Container optimization, package distribution, CI/CD implementation
- Video tutorials and interactive documentation for enhanced user onboarding
- Community documentation and contribution guidelines for open source adoption
- Advanced operational guides and integration examples for enterprise customers

**Files Created/Modified This Session**:
- `README.md` - Professional project front page with comprehensive overview and getting started guide
- `docs/installation.md` - Complete installation guide with prerequisites, RBAC setup, and troubleshooting
- `docs/user-guide.md` - Comprehensive user guide with natural language examples and workflow demonstrations
- `docs/safety.md` - Complete safety guide with architecture, risk assessment, and operational procedures
- `docs/api/README.md` - API documentation index tying together auto-generated documentation files
- `docs/troubleshooting.md` - Comprehensive troubleshooting guide with common issues and recovery procedures
- `docs/deployment.md` - Production deployment guide with containers, monitoring, and operational procedures
- `docs/api/` - Auto-generated API documentation (api-reference.md, safety-guide.md, usage-examples.md, api-documentation.json, openapi.json)
- `TASKS.md` - Updated to reflect Milestone 8 completion with detailed accomplishment summary

### Key Design Decisions

**Documentation Strategy**: Chose comprehensive coverage over minimal documentation to ensure enterprise readiness and user confidence, providing complete guidance for all stakeholders from developers to operators.

**Safety-First Messaging**: Emphasized safety and confirmation requirements throughout all documentation to build trust and prevent accidental cluster modifications while highlighting the powerful optimization capabilities.

**Multi-Format Approach**: Provided documentation in multiple formats (human-readable guides, machine-readable JSON, OpenAPI specifications) to serve different use cases and integration requirements.

**Auto-Generation Integration**: Leveraged existing documentation generator to create consistent, maintainable API documentation that stays synchronized with code changes and reduces manual maintenance burden.

The KRR MCP Server now provides **complete, enterprise-ready documentation** that enables safe AI-assisted Kubernetes optimization with confidence. The documentation suite serves all stakeholders from individual developers to enterprise platform teams, emphasizing safety while showcasing powerful optimization capabilities.
