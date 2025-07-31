# Changelog

All notable changes to the KRR MCP Server project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Docker containerization with multi-stage builds and security hardening
- PyPI package distribution with uvx compatibility
- Docker Compose configuration for development and testing
- Production-ready deployment configurations

## [0.1.0] - 2025-01-31

### Added
- Initial release of KRR MCP Server
- Complete MCP server implementation with FastMCP
- Integration with krr CLI for Kubernetes resource recommendations
- Comprehensive safety module with confirmation workflows
- Advanced kubectl executor with staged rollout and post-execution validation
- Complete test suite with real Kubernetes cluster integration
- Documentation and user guides
- Tool versioning and API documentation generation

### Security
- Safety-first design requiring explicit user confirmation for all changes
- Comprehensive audit trail for all operations
- Rollback capabilities for all applied changes
- Input validation and error handling throughout

### Features
- **Safety Module**: User confirmation workflows, safety validation, audit trails
- **Recommender Module**: krr CLI integration, recommendation filtering, caching
- **Executor Module**: kubectl operations, staged rollouts, transaction support
- **MCP Tools**: Complete set of MCP-compliant tools for AI assistant integration
- **Testing**: 78+ tests with integration, performance, and chaos testing
- **Documentation**: Complete user guides, API documentation, and safety documentation

### Technical
- Python 3.12+ with async/await throughout
- FastMCP for MCP protocol handling
- Pydantic for data validation
- Structured logging with audit capabilities
- Comprehensive error handling and recovery

[Unreleased]: https://github.com/krr-mcp/krr-mcp-server/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/krr-mcp/krr-mcp-server/releases/tag/v0.1.0
