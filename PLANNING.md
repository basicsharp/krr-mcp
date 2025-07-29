
# PLANNING.md - KRR MCP Server Project

## 1. Vision

### Project Purpose
The KRR MCP Server project aims to create a secure, user-controlled interface between AI assistants and Kubernetes resource optimization through the krr (Kubernetes Resource Recommender) tool. By implementing the Model Context Protocol (MCP), we enable AI assistants to safely analyze, recommend, and help apply resource optimizations while maintaining strict human oversight and approval workflows.

### Core Goals
1. **Safety-First Design**: Every recommendation application requires explicit user confirmation
2. **Transparency**: Clear visibility into all proposed changes before execution
3. **Reversibility**: Built-in rollback capabilities for all applied changes
4. **Integration**: Seamless interaction between AI assistants and krr functionality
5. **Auditability**: Comprehensive logging of all recommendations and actions

### Target Users
- DevOps engineers seeking AI-assisted Kubernetes optimization
- Platform teams wanting safe automation for resource management
- Organizations requiring approval workflows for infrastructure changes

### Success Metrics
- Zero unintended resource modifications
- 100% user confirmation rate before changes
- Complete audit trail for all recommendations
- Reduced time to analyze and apply optimizations
- Enhanced safety compared to manual CLI operations

## 2. Architecture

### System Design Overview

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

### Component Interactions

#### 1. MCP Server Core
- **Responsibility**: Handle MCP protocol communication
- **Interactions**: Receives commands from AI, routes to appropriate modules
- **Key Methods**: 
  - `handle_request()`: Process incoming MCP requests
  - `send_response()`: Format and return MCP responses

#### 2. Safety Module
- **Responsibility**: Enforce confirmation workflows and safety checks
- **Interactions**: Intercepts all execution requests
- **Key Methods**:
  - `require_confirmation()`: Present changes for user approval
  - `validate_changes()`: Check resource limits and constraints
  - `create_safety_report()`: Generate impact analysis

#### 3. Recommender Module
- **Responsibility**: Interface with krr for recommendations
- **Interactions**: Calls krr CLI, parses results
- **Key Methods**:
  - `get_recommendations()`: Execute krr scan
  - `parse_recommendations()`: Convert krr output to structured data
  - `filter_recommendations()`: Apply user-defined filters

#### 4. Executor Module
- **Responsibility**: Apply approved changes to cluster
- **Interactions**: Uses kubectl for modifications
- **Key Methods**:
  - `dry_run()`: Simulate changes without applying
  - `apply_with_rollback()`: Execute with rollback preparation
  - `rollback_changes()`: Revert to previous state

### Data Flow
1. AI assistant sends recommendation request via MCP
2. Server queries krr for current recommendations
3. Safety module analyzes proposed changes
4. User confirmation prompt generated
5. Upon approval, executor applies changes with rollback preparation
6. Status and results returned to AI assistant

## 3. Technology Stack

### Core Technologies

#### Python 3.12+
- **Version**: 3.12.0 or higher
- **Justification**: Latest stable version with enhanced async performance, improved error messages, and type annotation support critical for MCP server reliability

#### FastMCP 0.5+
- **Version**: 0.5.0 or higher
- **Justification**: Purpose-built for MCP servers, provides async support, built-in validation, and simplified protocol handling

#### krr CLI 1.7+
- **Version**: 1.7.0 or higher
- **Justification**: Latest stable version with JSON output support, comprehensive recommendation engine, and Prometheus integration

#### uv 0.4+
- **Version**: 0.4.0 or higher
- **Justification**: Modern Python package manager with faster dependency resolution, built-in virtual environment management, and reproducible builds

### Supporting Libraries

#### httpx 0.27+
- **Version**: 0.27.0 or higher
- **Purpose**: Async HTTP client for API interactions
- **Justification**: Modern async support, better than requests for MCP use case

#### pydantic 2.6+
- **Version**: 2.6.0 or higher
- **Purpose**: Data validation and settings management
- **Justification**: V2 offers 17x performance improvement, better validation

#### structlog 24.1+
- **Version**: 24.1.0 or higher
- **Purpose**: Structured logging for audit trails
- **Justification**: JSON logging, context preservation, async support

#### pytest 8.0+
- **Version**: 8.0.0 or higher
- **Purpose**: Testing framework
- **Justification**: Latest features for async testing, better fixtures

#### pytest-asyncio 0.23+
- **Version**: 0.23.0 or higher
- **Purpose**: Async test support
- **Justification**: Required for testing MCP async handlers

## 4. Required Tools

### Development Environment

#### Python Installation
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev

# macOS (using Homebrew)
brew install python@3.12

# Windows (using winget)
winget install Python.Python.3.12
```

#### uv Package Manager
```bash
# All platforms
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv
```

#### kubectl
```bash
# Latest stable version
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Verify installation
kubectl version --client
```

#### krr Installation
```bash
# Using pip
pip install krr

# Or using uv
uv pip install krr

# Verify installation
krr --version
```

### Development Tools

#### VS Code Extensions
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Python Test Explorer
- YAML (redhat.vscode-yaml)
- Kubernetes (ms-kubernetes-tools.vscode-kubernetes-tools)

#### Pre-commit Hooks
```bash
# Install pre-commit
pip install pre-commit

# Required .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
  
  - repo: https://github.com/psf/black
    rev: 24.2.0
    hooks:
      - id: black
  
  - repo: https://github.com/pycqa/isort
    rev: 5.13.0
    hooks:
      - id: isort
  
  - repo: https://github.com/PyCQA/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
```

### Testing Requirements

#### Test Kubernetes Cluster Options
1. **kind (Kubernetes in Docker)**
   ```bash
   # Install kind
   curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64
   chmod +x ./kind
   sudo mv ./kind /usr/local/bin/kind
   
   # Create test cluster
   kind create cluster --name krr-test
   ```

2. **minikube**
   ```bash
   # Install minikube
   curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
   sudo install minikube-linux-amd64 /usr/local/bin/minikube
   
   # Start cluster
   minikube start
   ```

#### Monitoring Stack (for krr testing)
```bash
# Prometheus installation (required for krr)
kubectl create namespace monitoring
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/bundle.yaml

# Or using Helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring
```

### Security Tools

#### Security Scanning
```bash
# bandit for Python security
pip install bandit

# safety for dependency scanning  
pip install safety

# Run security checks
bandit -r src/
safety check
```

### Documentation Tools

#### MkDocs for Documentation
```bash
# Install MkDocs with Material theme
pip install mkdocs mkdocs-material mkdocs-mermaid2-plugin

# Serve documentation locally
mkdocs serve
```

### Continuous Integration Requirements

#### GitHub Actions Runner Requirements
- Python 3.12+
- kubectl access to test cluster
- Prometheus endpoint for krr testing
- Docker for container builds

#### Required Secrets
- `KUBECONFIG`: Base64 encoded kubeconfig for test cluster
- `PROMETHEUS_URL`: URL for Prometheus instance
- `MCP_SERVER_TOKEN`: Authentication token for MCP server

This planning document provides the foundation for implementing a safe, reliable MCP server for krr that prioritizes user control and security while enabling powerful AI-assisted Kubernetes optimization workflows.
