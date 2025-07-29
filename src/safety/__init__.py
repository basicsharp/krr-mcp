"""Safety module for KRR MCP Server.

This module provides comprehensive safety controls for Kubernetes resource modifications:
- User confirmation workflows
- Change validation and risk assessment
- Rollback capabilities
- Audit trail management

CRITICAL: All cluster modifications must pass through this module's safety checks.
"""
