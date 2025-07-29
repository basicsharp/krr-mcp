# Troubleshooting Guide

Comprehensive troubleshooting guide for the krr MCP Server, covering common issues, error messages, and solutions.

## 🔍 Quick Diagnostic Steps

When experiencing issues, start with these basic diagnostic steps:

### 1. System Health Check

```bash
# Check server status
uv run python main.py --health-check

# Test component availability
uv run python -c "
from src.server import KrrMCPServer, ServerConfig
from src.recommender.krr_client import KrrClient
import asyncio

async def quick_test():
    config = ServerConfig()
    client = KrrClient(config)
    
    print('Testing krr availability...')
    krr_ok = await client.check_krr_availability()
    print(f'krr: {"✅ Available" if krr_ok else "❌ Not available"}')
    
    print('Testing kubectl availability...')
    kubectl_ok = await client.check_kubectl_availability()
    print(f'kubectl: {"✅ Available" if kubectl_ok else "❌ Not available"}')

asyncio.run(quick_test())
"
```

### 2. Configuration Validation

```bash
# Check environment variables
env | grep -E "(KUBECONFIG|PROMETHEUS_URL|KRR_)" | sort

# Test Kubernetes connectivity
kubectl cluster-info
kubectl get nodes

# Test Prometheus connectivity
curl -s "${PROMETHEUS_URL}/api/v1/query?query=up" | jq .status
```

### 3. Log Analysis

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
export DEVELOPMENT_MODE=true

# Check recent logs
tail -f logs/krr-mcp-server.log

# Search for specific errors
grep -E "(ERROR|CRITICAL)" logs/krr-mcp-server.log | tail -20
```

## 🚨 Common Error Messages

### Installation and Setup Issues

#### Error: "krr command not found"

**Symptoms:**
```
2025-01-29 14:30:52 [error] krr binary not found in PATH
FileNotFoundError: krr
```

**Causes:**
- krr CLI tool not installed
- krr not in system PATH
- Virtual environment issues

**Solutions:**

1. **Install krr:**
```bash
# Using pip
pip install krr

# Using uv
uv add krr

# Verify installation
which krr
krr --version
```

2. **Check PATH:**
```bash
# Add to PATH if needed
export PATH="$HOME/.local/bin:$PATH"

# Or use full path in config
export KRR_BINARY_PATH="/full/path/to/krr"
```

3. **Virtual environment:**
```bash
# Ensure uv environment is active
uv sync
uv run which krr
```

#### Error: "Permission denied accessing kubeconfig"

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: '/path/to/kubeconfig'
```

**Solutions:**

1. **Fix file permissions:**
```bash
chmod 600 ~/.kube/config
```

2. **Verify KUBECONFIG path:**
```bash
echo $KUBECONFIG
ls -la $KUBECONFIG
```

3. **Use correct context:**
```bash
kubectl config current-context
kubectl config use-context your-cluster
```

### Kubernetes Connectivity Issues

#### Error: "Unable to connect to the server"

**Symptoms:**
```
Unable to connect to the server: dial tcp: lookup kubernetes.default.svc.cluster.local: no such host
```

**Causes:**
- Invalid kubeconfig
- Cluster not accessible
- Network connectivity issues
- Expired certificates

**Solutions:**

1. **Test basic connectivity:**
```bash
kubectl cluster-info
kubectl get nodes
```

2. **Update kubeconfig:**
```bash
# AWS EKS
aws eks update-kubeconfig --name your-cluster

# Azure AKS
az aks get-credentials --resource-group rg --name cluster

# Google GKE
gcloud container clusters get-credentials cluster --zone zone
```

3. **Check network access:**
```bash
# Test cluster endpoint
curl -k https://your-cluster-endpoint/api/v1/

# Check firewall/proxy settings
```

#### Error: "Forbidden: User cannot list resource"

**Symptoms:**
```
pods is forbidden: User "system:serviceaccount:default:default" cannot list resource "pods" in API group "" at the cluster scope
```

**Causes:**
- Insufficient RBAC permissions
- Wrong service account
- Missing ClusterRole/ClusterRoleBinding

**Solutions:**

1. **Apply RBAC configuration:**
```bash
# Create the required RBAC (see installation guide)
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: krr-mcp-server
rules:
- apiGroups: [""]
  resources: ["pods", "nodes", "namespaces"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets", "daemonsets", "statefulsets"]
  verbs: ["get", "list", "watch", "patch", "update"]
EOF
```

2. **Check current permissions:**
```bash
kubectl auth can-i list pods
kubectl auth can-i patch deployments
```

3. **Use service account:**
```bash
kubectl create serviceaccount krr-mcp-server
kubectl create clusterrolebinding krr-mcp-server \
  --clusterrole=krr-mcp-server \
  --serviceaccount=default:krr-mcp-server
```

### Prometheus Integration Issues

#### Error: "Failed to connect to Prometheus"

**Symptoms:**
```
PrometheusConnectionError: Failed to connect to Prometheus at http://prometheus:9090
Connection refused
```

**Causes:**
- Prometheus not running
- Wrong Prometheus URL
- Network connectivity issues
- Authentication required

**Solutions:**

1. **Verify Prometheus is running:**
```bash
kubectl get pods -n monitoring | grep prometheus
kubectl get svc -n monitoring | grep prometheus
```

2. **Test Prometheus connectivity:**
```bash
# Port forward to test locally
kubectl port-forward -n monitoring svc/prometheus-server 9090:80

# Test query
curl "http://localhost:9090/api/v1/query?query=up"
```

3. **Update Prometheus URL:**
```bash
# Common URLs for different setups
export PROMETHEUS_URL="http://prometheus.monitoring.svc.cluster.local:9090"
export PROMETHEUS_URL="http://prometheus-server.monitoring.svc.cluster.local:80"
export PROMETHEUS_URL="http://localhost:9090"  # For port-forward
```

4. **Check authentication:**
```bash
# If Prometheus requires auth
export PROMETHEUS_URL="http://username:password@prometheus:9090"
```

#### Error: "No metric data available"

**Symptoms:**
```
2025-01-29 14:30:52 [warning] No metrics found for namespace: default
krr returned empty recommendations
```

**Causes:**
- Insufficient metrics history
- Metrics collection not configured
- Wrong time range for query

**Solutions:**

1. **Check metrics availability:**
```bash
# Verify metrics are being collected
curl -s "${PROMETHEUS_URL}/api/v1/query?query=container_cpu_usage_seconds_total" | jq .

# Check specific workload metrics
curl -s "${PROMETHEUS_URL}/api/v1/query?query=container_memory_usage_bytes{namespace=\"default\"}" | jq .
```

2. **Adjust time range:**
```bash
# Use shorter history duration
export KRR_HISTORY_DURATION=24h  # Instead of 7d

# Wait for more metrics to accumulate
```

3. **Verify monitoring setup:**
```bash
# Check if monitoring is properly configured
kubectl get servicemonitor -A
kubectl get podmonitor -A
```

### MCP Integration Issues

#### Error: "MCP server not responding"

**Symptoms:**
- Claude shows "Server not available"
- Connection timeouts
- No tools listed

**Solutions:**

1. **Check server process:**
```bash
# Test server startup
uv run python main.py

# Check for startup errors
```

2. **Verify MCP configuration:**
```json
{
  "mcpServers": {
    "krr-mcp": {
      "command": "uv",
      "args": ["run", "python", "/absolute/path/to/krr-mcp/main.py"],
      "env": {
        "KUBECONFIG": "/path/to/kubeconfig",
        "PROMETHEUS_URL": "http://prometheus:9090"
      }
    }
  }
}
```

3. **Test MCP client connection:**
```bash
# Manual MCP client test
uv run python scripts/test_mcp_client.py
```

#### Error: "Tool execution failed"

**Symptoms:**
```
Tool execution failed: Internal server error
Component not available: krr_client
```

**Causes:**
- Missing dependencies
- Component initialization failure
- Configuration errors

**Solutions:**

1. **Check component status:**
```bash
uv run python -c "
from src.server import KrrMCPServer, ServerConfig
import asyncio

async def test_components():
    config = ServerConfig()
    server = KrrMCPServer(config)
    await asyncio.sleep(2)  # Wait for initialization
    
    print(f'krr_client: {\"OK\" if server.krr_client else \"FAILED\"}')
    print(f'confirmation_manager: {\"OK\" if server.confirmation_manager else \"FAILED\"}')
    print(f'kubectl_executor: {\"OK\" if server.kubectl_executor else \"FAILED\"}')

asyncio.run(test_components())
"
```

2. **Restart with debug mode:**
```bash
export LOG_LEVEL=DEBUG
uv run python main.py
```

### Safety and Security Issues

#### Error: "Confirmation token expired"

**Symptoms:**
```
InvalidTokenError: Confirmation token has expired
Token expires at: 2025-01-29T16:35:00Z
Current time: 2025-01-29T16:40:00Z
```

**Causes:**
- Token expired (default 5 minutes)
- System clock skew
- Long delays between confirmation and execution

**Solutions:**

1. **Request new confirmation:**
```bash
# AI will need to request fresh confirmation
"Please request confirmation again for these changes"
```

2. **Adjust timeout (if needed):**
```bash
# Extend timeout for complex operations
export CONFIRMATION_TIMEOUT_SECONDS=600  # 10 minutes
```

3. **Check system time:**
```bash
# Ensure system clocks are synchronized
date
ntpdate -q pool.ntp.org
```

#### Error: "Safety violation detected"

**Symptoms:**
```
SafetyViolationError: Resource change exceeds maximum allowed limit
Memory change: 1Gi → 8Gi (+700%)
Maximum allowed: 500%
```

**Causes:**
- Changes exceed safety limits
- Critical workload protection
- Production namespace restrictions

**Solutions:**

1. **Use smaller incremental changes:**
```bash
# Instead of 1Gi → 8Gi in one step
# Do: 1Gi → 3Gi → 6Gi → 8Gi in steps
```

2. **Adjust safety limits (carefully):**
```bash
# Temporarily increase limit for specific operation
export MAX_RESOURCE_CHANGE_PERCENT=1000
```

3. **Use manual kubectl for extreme cases:**
```bash
# For changes that must exceed safety limits
kubectl patch deployment myapp --patch '{"spec":{"template":{"spec":{"containers":[{"name":"app","resources":{"requests":{"memory":"8Gi"}}}]}}}}'
```

## 🐛 Debugging Techniques

### Enable Debug Logging

```bash
# Full debug output
export LOG_LEVEL=DEBUG
export DEVELOPMENT_MODE=true

# Component-specific debugging
export DEBUG_KRR_CLIENT=true
export DEBUG_SAFETY_MODULE=true
export DEBUG_KUBECTL_EXECUTOR=true
```

### Component Testing

```bash
# Test krr client in isolation
uv run python -c "
from src.recommender.krr_client import KrrClient
from src.server import ServerConfig
import asyncio

async def test_krr():
    config = ServerConfig()
    client = KrrClient(config)
    
    try:
        result = await client.get_recommendations('default', 'simple')
        print(f'krr test: SUCCESS - {len(result.recommendations)} recommendations')
    except Exception as e:
        print(f'krr test: FAILED - {e}')

asyncio.run(test_krr())
"

# Test safety module
uv run python -c "
from src.safety.confirmation_manager import ConfirmationManager
from src.safety.models import ResourceChange, ChangeType
from src.server import ServerConfig

config = ServerConfig()
manager = ConfirmationManager(config)

change = ResourceChange(
    resource_name='test-deployment',
    namespace='default',
    change_type=ChangeType.RESOURCE_LIMITS,
    current_cpu='100m',
    recommended_cpu='200m',
    current_memory='128Mi',
    recommended_memory='256Mi'
)

try:
    result = manager.request_confirmation([change], 'medium')
    print(f'Safety test: SUCCESS - Token: {result.confirmation_token[:8]}...')
except Exception as e:
    print(f'Safety test: FAILED - {e}')
"
```

### Network Debugging

```bash
# Test cluster connectivity
kubectl proxy --port=8080 &
curl http://localhost:8080/api/v1/namespaces

# Test Prometheus connectivity
curl -v "${PROMETHEUS_URL}/api/v1/status/config"

# DNS resolution test
nslookup kubernetes.default.svc.cluster.local
```

### Performance Debugging

```bash
# Monitor resource usage
top -p $(pgrep -f "krr-mcp")

# Profile memory usage
uv run python -m memory_profiler main.py

# Monitor file descriptors
lsof -p $(pgrep -f "krr-mcp")
```

## 🔧 Recovery Procedures

### Reset System State

```bash
# Clear all tokens and snapshots
uv run python scripts/cleanup_system.py

# Reset configuration to defaults
rm .env
cp .env.example .env
```

### Emergency Rollback

```bash
# List recent changes
uv run python scripts/list_recent_changes.py

# Emergency rollback of specific change
uv run python scripts/emergency_rollback.py --change-id ch_20250129_143055_web-app

# Rollback all changes from last hour
uv run python scripts/emergency_rollback.py --since "1 hour ago"
```

### Database Recovery

If audit logs or snapshots are corrupted:

```bash
# Backup current state
cp -r logs/ logs_backup_$(date +%Y%m%d_%H%M%S)

# Rebuild audit log index
uv run python scripts/rebuild_audit_index.py

# Verify log integrity
uv run python scripts/verify_audit_logs.py
```

## 📊 Monitoring and Alerting

### Health Monitoring

```bash
# Continuous health check
while true; do
  uv run python main.py --health-check
  sleep 60
done

# Export metrics for monitoring
uv run python scripts/export_metrics.py --format prometheus
```

### Alert Conditions

Monitor these conditions for potential issues:

- **High error rate**: >5% of operations failing
- **Token expiration rate**: >20% of tokens expiring unused
- **Rollback frequency**: >10% of changes being rolled back
- **Component availability**: Any component down for >1 minute
- **Memory usage**: >80% of available memory
- **Disk space**: <10% free space for logs/snapshots

## 🆘 Getting Additional Help

### Before Contacting Support

1. **Gather diagnostic information:**
```bash
# Generate comprehensive diagnostic report
uv run python scripts/diagnostic_report.py --output diagnostic-$(date +%Y%m%d_%H%M%S).zip
```

2. **Check known issues:**
   - Review [GitHub Issues](https://github.com/your-org/krr-mcp/issues)
   - Search project documentation
   - Check community discussions

3. **Prepare information:**
   - Error messages and logs
   - System configuration
   - Steps to reproduce
   - Expected vs actual behavior

### Support Channels

- **GitHub Issues**: [Report bugs and request features](https://github.com/your-org/krr-mcp/issues)
- **Community**: Join our Discord/Slack for questions
- **Security Issues**: Email security@yourorg.com
- **Enterprise Support**: Contact enterprise@yourorg.com

### Contributing Fixes

If you find a solution to an issue:

1. **Test the fix thoroughly**
2. **Document the solution**
3. **Submit a pull request**
4. **Update documentation**

## 📚 Related Resources

- **[Installation Guide](installation.md)** - Setup and configuration
- **[User Guide](user-guide.md)** - Usage patterns and best practices
- **[Safety Guide](safety.md)** - Understanding safety features
- **[API Reference](api/README.md)** - Technical details

---

**Remember**: Most issues are configuration-related. Double-check your setup against the installation guide, and don't hesitate to ask for help in the community channels. 