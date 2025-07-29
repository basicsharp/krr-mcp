# Installation Guide

Complete installation instructions for the KRR MCP Server, including all prerequisites and configuration options.

## 📋 Prerequisites

### System Requirements

- **Operating System**: Linux, macOS, or Windows
- **Python**: 3.12 or higher
- **Memory**: 512MB minimum, 2GB recommended for large clusters
- **Disk Space**: 100MB for installation, additional space for logs and snapshots

### Required Tools

#### 1. Python 3.12+

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev
```

**macOS (Homebrew):**
```bash
brew install python@3.12
```

**Windows (winget):**
```bash
winget install Python.Python.3.12
```

**Verify installation:**
```bash
python3.12 --version  # Should show 3.12.x or higher
```

#### 2. uv Package Manager (Recommended)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv

# Verify installation
uv --version
```

#### 3. kubectl

```bash
# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# macOS (Homebrew)
brew install kubectl

# Windows (winget)
winget install Kubernetes.kubectl

# Verify installation
kubectl version --client
```

#### 4. krr CLI Tool

```bash
# Using pip
pip install krr

# Using uv
uv pip install krr

# Verify installation
krr --version
```

### Kubernetes Requirements

#### Cluster Access
- Valid kubeconfig file with cluster access
- kubectl context configured for target cluster
- Sufficient RBAC permissions (see [RBAC Setup](#rbac-setup))

#### Prometheus Installation
krr requires Prometheus to analyze resource usage:

**Using Helm (Recommended):**
```bash
# Add Prometheus Helm repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install Prometheus stack
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --set prometheus.prometheusSpec.retention=7d
```

**Verify Prometheus is running:**
```bash
kubectl get pods -n monitoring | grep prometheus
```

## 🚀 Installation Methods

### Method 1: From Source (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/krr-mcp.git
cd krr-mcp

# 2. Install with uv
uv sync

# 3. Verify installation
uv run python main.py --help
```

### Method 2: Using pip

```bash
# Install directly from git
pip install git+https://github.com/your-org/krr-mcp.git

# Or from PyPI (when available)
pip install krr-mcp-server
```

### Method 3: Docker (Coming Soon)

```bash
# Pull the Docker image
docker pull your-org/krr-mcp:latest

# Run the container
docker run -d \
  --name krr-mcp \
  -v ~/.kube/config:/root/.kube/config:ro \
  -e PROMETHEUS_URL=http://prometheus.monitoring.svc.cluster.local:9090 \
  your-org/krr-mcp:latest
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Kubernetes Configuration
KUBECONFIG=/path/to/your/kubeconfig
KUBERNETES_CONTEXT=my-cluster

# Prometheus Configuration (Required)
PROMETHEUS_URL=http://prometheus.monitoring.svc.cluster.local:9090

# krr Configuration
KRR_STRATEGY=simple
KRR_HISTORY_DURATION=7d

# Server Configuration
LOG_LEVEL=INFO
CONFIRMATION_TIMEOUT_SECONDS=300
MAX_RESOURCE_CHANGE_PERCENT=500
ROLLBACK_RETENTION_DAYS=7

# Safety Configuration
CRITICAL_WORKLOAD_PATTERNS=postgres,mysql,redis,controller,operator
PRODUCTION_NAMESPACE_PATTERNS=prod,production,live

# Development Settings (Optional)
DEVELOPMENT_MODE=false
MOCK_KRR_RESPONSES=false
MOCK_KUBECTL_COMMANDS=false
```

### Configuration File

Alternatively, create a `config.yaml`:

```yaml
kubernetes:
  kubeconfig: ~/.kube/config
  context: my-cluster

prometheus:
  url: http://prometheus.monitoring.svc.cluster.local:9090

krr:
  strategy: simple
  history_duration: 7d

server:
  log_level: INFO
  confirmation_timeout_seconds: 300
  max_resource_change_percent: 500
  rollback_retention_days: 7

safety:
  critical_workload_patterns:
    - postgres
    - mysql
    - redis
    - controller
    - operator
  production_namespaces:
    - prod
    - production
    - live
```

## 🔐 RBAC Setup

The KRR MCP Server requires specific Kubernetes permissions:

### ServiceAccount and ClusterRole

```yaml
# serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: krr-mcp-server
  namespace: default

---
# clusterrole.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: krr-mcp-server
rules:
# Read access for recommendations
- apiGroups: [""]
  resources: ["pods", "nodes", "namespaces"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets", "daemonsets", "statefulsets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["metrics.k8s.io"]
  resources: ["pods", "nodes"]
  verbs: ["get", "list"]

# Write access for applying recommendations (use carefully)
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets", "statefulsets"]
  verbs: ["patch", "update"]

---
# clusterrolebinding.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: krr-mcp-server
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: krr-mcp-server
subjects:
- kind: ServiceAccount
  name: krr-mcp-server
  namespace: default
```

**Apply the RBAC configuration:**
```bash
kubectl apply -f serviceaccount.yaml
kubectl apply -f clusterrole.yaml
kubectl apply -f clusterrolebinding.yaml
```

### Minimal Permissions (Read-Only Mode)

For maximum security, use read-only permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: krr-mcp-server-readonly
rules:
- apiGroups: [""]
  resources: ["pods", "nodes", "namespaces"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets", "daemonsets", "statefulsets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["metrics.k8s.io"]
  resources: ["pods", "nodes"]
  verbs: ["get", "list"]
```

## 🧪 Testing Installation

### 1. Basic Health Check

```bash
# Test the installation
uv run python main.py --test

# Check component availability
uv run python -c "
from src.server import KrrMCPServer, ServerConfig
from src.recommender.krr_client import KrrClient
import asyncio

async def test():
    config = ServerConfig()
    krr_client = KrrClient(config)
    
    # Test krr availability
    available = await krr_client.check_krr_availability()
    print(f'krr available: {available}')
    
    # Test kubectl availability  
    kubectl_available = await krr_client.check_kubectl_availability()
    print(f'kubectl available: {kubectl_available}')

asyncio.run(test())
"
```

### 2. Connectivity Test

```bash
# Test Kubernetes connectivity
kubectl cluster-info

# Test Prometheus connectivity (replace URL with your Prometheus)
curl -s "http://prometheus.monitoring.svc.cluster.local:9090/api/v1/query?query=up" | jq .

# Test krr functionality
krr simple --dry-run
```

### 3. Run Test Suite

```bash
# Run the comprehensive test suite
uv run python scripts/run_tests.py

# Run only integration tests
uv run pytest tests/test_integration* -v

# Check test coverage
uv run pytest --cov=src --cov-report=html
```

## 🔗 MCP Integration

### Claude Desktop Setup

1. **Locate Claude Desktop config file:**
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. **Add KRR MCP Server configuration:**
```json
{
  "mcpServers": {
    "krr-mcp": {
      "command": "uv",
      "args": ["run", "python", "/absolute/path/to/krr-mcp/main.py"],
      "env": {
        "KUBECONFIG": "/path/to/your/kubeconfig",
        "PROMETHEUS_URL": "http://prometheus.monitoring.svc.cluster.local:9090",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

3. **Restart Claude Desktop** and verify the server appears in the tools list.

### Other MCP Clients

For custom MCP clients, connect to the server using stdio transport:

```python
from mcp import ClientSession, StdioServerParameters
import asyncio

async def connect_to_krr_mcp():
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "/path/to/krr-mcp/main.py"],
        env={
            "KUBECONFIG": "/path/to/kubeconfig",
            "PROMETHEUS_URL": "http://prometheus:9090"
        }
    )
    
    async with ClientSession(server_params) as session:
        # List available tools
        tools = await session.list_tools()
        print(f"Available tools: {[tool.name for tool in tools.tools]}")

asyncio.run(connect_to_krr_mcp())
```

## 🔧 Troubleshooting

### Common Issues

#### 1. krr Not Found
```
Error: krr command not found
```
**Solution:**
```bash
# Install krr
pip install krr

# Verify installation
which krr
krr --version
```

#### 2. Prometheus Connection Failed  
```
Error: Failed to connect to Prometheus at http://prometheus:9090
```
**Solutions:**
```bash
# Check Prometheus is running
kubectl get pods -n monitoring | grep prometheus

# Test connectivity
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
curl http://localhost:9090/api/v1/query?query=up

# Update PROMETHEUS_URL in your config
export PROMETHEUS_URL=http://localhost:9090
```

#### 3. Kubernetes Permission Denied
```
Error: pods is forbidden: User "default" cannot list resource "pods"
```
**Solution:**
Apply the [RBAC configuration](#rbac-setup) above.

#### 4. Python Version Issues
```
Error: Python 3.12+ required
```
**Solution:**
```bash
# Check Python version
python --version

# Use specific Python version
python3.12 -m pip install uv
python3.12 -m uv sync
```

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
# Set debug logging
export LOG_LEVEL=DEBUG
export DEVELOPMENT_MODE=true

# Run with detailed output
uv run python main.py
```

### Logs and Diagnostics

```bash
# Check server logs
tail -f logs/krr-mcp-server.log

# Generate diagnostic report
uv run python scripts/diagnostic_report.py

# Test individual components
uv run python scripts/test_components.py
```

## 📝 Next Steps

After successful installation:

1. **Read the [User Guide](user-guide.md)** for usage instructions
2. **Review [Safety Features](safety.md)** to understand protection mechanisms  
3. **Check [API Documentation](api/README.md)** for detailed tool reference
4. **Test with non-production clusters first**
5. **Set up monitoring and alerting** for production use

## 🆘 Getting Help

- **Documentation**: Check our [comprehensive docs](../README.md)
- **Issues**: Report problems on [GitHub Issues](https://github.com/your-org/krr-mcp/issues)
- **Community**: Join our [Discord/Slack] for questions
- **Security**: Email security@yourorg.com for security issues

---

**⚠️ Important**: Always test the installation with non-production clusters first. The KRR MCP Server can modify cluster resources when given proper permissions. 