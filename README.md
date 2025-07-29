# KRR MCP Server

A safety-first MCP (Model Context Protocol) server that enables AI assistants to safely analyze and optimize Kubernetes resource usage through awesome [krr (Kubernetes Resource Recommender)](https://github.com/robusta-dev/krr).

[![Test Coverage](https://github.com/basicsharp/krr-mcp/actions/workflows/test-coverage.yml/badge.svg)](https://github.com/basicsharp/krr-mcp/actions/workflows/test-coverage.yml)
[![Security Scan](https://github.com/basicsharp/krr-mcp/actions/workflows/security.yml/badge.svg)](https://github.com/basicsharp/krr-mcp/actions/workflows/security.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

## 🚨 Safety First

**NO CLUSTER MODIFICATIONS WITHOUT EXPLICIT USER CONFIRMATION**

This server implements bulletproof safety controls:
- ✅ **Explicit Confirmation Required**: Every change requires user approval with detailed impact analysis
- ✅ **Complete Audit Trail**: All operations logged for compliance and troubleshooting
- ✅ **Automatic Rollback**: Changes can be reverted with one command
- ✅ **Production Protection**: Enhanced safeguards for critical workloads
- ✅ **Risk Assessment**: Multi-factor analysis prevents dangerous modifications

## 🎯 What This Does

The KRR MCP Server bridges AI assistants (like Claude) with Kubernetes optimization:

1. **📊 Analyze Resource Usage**: Get krr recommendations through natural language
2. **🔍 Preview Changes**: See exactly what would change before applying
3. **✋ Require Confirmation**: Human approval for all cluster modifications
4. **⚡ Apply Safely**: Execute changes with automatic rollback preparation
5. **📝 Maintain Records**: Complete audit trail of all operations

## ⚡ Quick Start

### Prerequisites

- Python 3.12+
- kubectl configured for your cluster
- [krr CLI tool](https://github.com/robusta-dev/krr) installed
- Prometheus running in your cluster (for krr)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/krr-mcp.git
cd krr-mcp

# Install with uv (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Or with pip
pip install -e .
```

### Basic Usage

1. **Start the MCP server:**
```bash
uv run python main.py
```

2. **Connect with Claude Desktop** (add to `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "krr-mcp": {
      "command": "uv",
      "args": ["run", "python", "/path/to/krr-mcp/main.py"],
      "env": {
        "KUBECONFIG": "/path/to/your/kubeconfig"
      }
    }
  }
}
```

3. **Start optimizing with AI assistance:**
```
"Analyze resource usage in my production namespace and show me potential optimizations"
```

## 🛡️ Safety Features

### Confirmation Workflow

Every cluster modification follows this safety flow:

```
1. AI Request → 2. krr Analysis → 3. Safety Assessment → 4. User Confirmation → 5. Safe Execution
                                                      ↓
                                        🚫 NO CONFIRMATION = NO CHANGES
```

### Example Confirmation Prompt

```
RESOURCE OPTIMIZATION CONFIRMATION

The following changes will be applied to cluster 'production':

Deployment: web-app (namespace: default)
- CPU Request: 100m → 250m (+150%)
- Memory Request: 128Mi → 256Mi (+100%)

Impact Analysis:
- Pods affected: 3
- Potential restart required: Yes
- Risk level: MEDIUM
- Estimated monthly cost change: +$45

Rollback snapshot: web-app-20250129-143052

Do you want to proceed? (yes/no):
```

### Built-in Protections

- **Resource Limits**: Prevents extreme changes (>500% increases)
- **Critical Workload Detection**: Extra protection for databases, controllers
- **Production Namespace Awareness**: Enhanced safeguards for prod environments
- **Token Expiration**: Confirmation tokens expire after 5 minutes
- **Single-Use Tokens**: Each approval is valid for one operation only

## 🧰 MCP Tools

The server provides 9 MCP tools for comprehensive resource management:

| Tool | Purpose | Safety Level |
|------|---------|--------------|
| `scan_recommendations` | Get krr optimization recommendations | Read-only |
| `preview_changes` | Show what would change | Analysis only |
| `request_confirmation` | Get user approval for changes | **Confirmation required** |
| `apply_recommendations` | Execute approved changes | **Requires valid token** |
| `rollback_changes` | Revert to previous state | **Requires confirmation** |
| `get_safety_report` | Analyze change risks | Analysis only |
| `get_execution_history` | View audit trail | Read-only |
| `generate_documentation` | Generate API docs | Read-only |
| `get_tool_versions` | Check tool versions | Read-only |

## 📖 Documentation

- **[Installation Guide](docs/installation.md)** - Complete setup instructions
- **[User Guide](docs/user-guide.md)** - How to use with AI assistants
- **[API Reference](docs/api/README.md)** - Complete tool documentation
- **[Safety Guide](docs/safety.md)** - Understanding safety features
- **[Deployment Guide](docs/deployment.md)** - Production deployment
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions

## 🚀 Features

### AI-Powered Analysis
- Natural language queries for resource optimization
- Intelligent recommendation filtering and prioritization
- Context-aware safety assessments

### Enterprise-Ready Safety
- Multi-layer validation prevents dangerous changes
- Complete audit trails for compliance
- Automatic rollback snapshots before changes
- Production workload protection

### Developer Experience
- Comprehensive test suite (90+ tests, 95%+ safety coverage)
- Mock modes for safe development
- Structured logging with JSON output
- Type-safe with Pydantic models

### Kubernetes Integration
- Works with any Kubernetes cluster
- Supports all krr strategies (simple, simple_limit)
- kubectl integration with transaction support
- Prometheus-based recommendations

## 🔧 Configuration

Key environment variables:

```bash
# Kubernetes configuration
KUBECONFIG=/path/to/kubeconfig
KUBERNETES_CONTEXT=my-cluster

# Prometheus (required by krr)
PROMETHEUS_URL=http://prometheus.monitoring.svc.cluster.local:9090

# Server settings
LOG_LEVEL=INFO
CONFIRMATION_TIMEOUT=300  # 5 minutes
MAX_RESOURCE_CHANGE_PERCENT=500  # Maximum allowed change

# Safety settings
CRITICAL_WORKLOAD_PATTERNS=postgres,mysql,redis,controller,operator
PRODUCTION_NAMESPACE_PATTERNS=prod,production,live
```

## Supported KRR Algorithms

KRR provides multiple strategies for calculating resource recommendations:

#### Simple Strategy (default)
By default, we use the _simple_ strategy (`krr simple`). It is calculated as follows (_The exact numbers can be customized in CLI arguments_):

- **CPU**: Request at the 95th percentile, **limit unset** (allows unlimited bursting)
- **Memory**: Maximum value over the past week + 15% buffer (same for request and limit)

#### Simple-Limit Strategy
The _simple-limit_ strategy (`krr simple_limit`) provides both CPU requests and limits:

- **CPU**: Request and limit both set to configurable percentiles (default 95th percentile for both)
- **Memory**: Maximum value over the past week + 15% buffer (same for request and limit)

**Key difference**: The simple strategy leaves CPU limits unset to allow unlimited bursting, while simple-limit sets explicit CPU limits.

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Run all tests
uv run python scripts/run_tests.py

# Run specific test categories
uv run pytest tests/test_safety* -v      # Safety-critical tests
uv run pytest tests/test_integration* -v # End-to-end workflows
uv run pytest tests/test_performance* -v # Performance benchmarks
uv run pytest tests/test_chaos* -v       # Chaos engineering

# Generate coverage report
uv run pytest --cov=src --cov-report=html
```

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   AI Assistant  │────▶│   MCP Protocol   │────▶│  KRR MCP Server │
│   (Claude/etc)  │◀────│    Interface     │◀────│   (FastMCP)     │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                        ┌──────────────────────────────────┼──────────────────────────────────┐
                        │                                  │                                  │
                   ┌────▼─────┐                    ┌──────▼──────┐                    ┌──────▼──────┐
                   │ Safety   │                    │ Recommender │                    │  Executor   │
                   │ Module   │                    │   Module    │                    │   Module    │
                   └────┬─────┘                    └──────┬──────┘                    └──────┬──────┘
                        │                                  │                                  │
                   ┌────▼─────┐                    ┌──────▼──────┐                    ┌──────▼──────┐
                   │Validation│                    │   krr CLI   │                    │  kubectl    │
                   │  Engine  │                    │  Interface  │                    │  Interface  │
                   └──────────┘                    └──────────────┘                    └──────────────┘
```

## 📊 Project Status

- ✅ **Milestone 1-4**: Foundation, Safety, and Core Features
- ✅ **Milestone 6**: Complete MCP Tools Implementation
- ✅ **Milestone 7**: Comprehensive Testing Suite
- 🚧 **Milestone 8**: Documentation (In Progress)
- ⏳ **Milestone 9**: Deployment and Distribution
- ⏳ **Milestone 10**: Maintenance and Community

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone and setup
git clone https://github.com/your-org/krr-mcp.git
cd krr-mcp
uv sync --dev

# Install pre-commit hooks
pre-commit install

# Run tests
uv run python scripts/run_tests.py
```

### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality and consistency. The hooks automatically run the same checks as our GitHub Actions workflow.

**Install pre-commit hooks:**
```bash
# Install dependencies
uv sync --group dev

# Install pre-commit hooks
uv run pre-commit install
```

**Available hooks:**
- **Code formatting**: Black and isort
- **Linting**: Flake8 (critical errors only)
- **Security**: Bandit security scanner
- **File maintenance**: Trailing whitespace, end-of-file fixes
- **Format validation**: YAML, JSON, TOML

**Manual execution:**
```bash
# Run on all files
uv run pre-commit run --all-files

# Run on staged files only
uv run pre-commit run
```

The hooks will automatically fix formatting issues and prevent commits that fail quality checks.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: Check our [comprehensive docs](docs/)
- **Issues**: Report bugs on [GitHub Issues](https://github.com/your-org/krr-mcp/issues)
- **Security**: Email security@yourorg.com for security vulnerabilities
- **Community**: Join our [Discord/Slack] for questions and discussions

## ⚠️ Important Notes

**This tool can modify your Kubernetes cluster resources.** Always:

1. 🧪 **Test in non-production first**
2. 📋 **Review all confirmations carefully**
3. 🔄 **Keep rollback capabilities ready**
4. 📊 **Monitor after changes**
5. 🛡️ **Use production namespace protections**

The KRR MCP Server is designed to make AI-assisted Kubernetes optimization both **powerful** and **safe**. Every feature prioritizes preventing accidental damage while enabling intelligent resource management.

---

**Made with ❤️ for safe AI-assisted Kubernetes optimization**
