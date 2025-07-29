"""Executor module for krr MCP Server.

This module provides safe execution of kubectl operations:
- Transaction-based resource updates
- Progress tracking and rollback capabilities
- Post-execution validation
- Comprehensive error recovery
"""