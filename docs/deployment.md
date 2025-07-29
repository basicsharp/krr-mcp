# Deployment Guide

Production deployment guide for the KRR MCP Server, covering container deployment, monitoring, security, and operational best practices.

## 🎯 Deployment Overview

This guide covers deploying the KRR MCP Server in production environments with proper security, monitoring, and operational controls.

### Deployment Options

1. **Container Deployment** - Docker/Kubernetes deployment (recommended)
2. **VM Deployment** - Traditional server deployment  
3. **Serverless Deployment** - Cloud functions (limited functionality)
4. **Hybrid Deployment** - Mix of approaches for different environments

## 🐳 Container Deployment

### Docker Image

#### Building the Image

```dockerfile
# Dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

# Install krr
RUN pip install krr

# Set working directory
WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY . .

# Install dependencies
RUN uv sync --frozen

# Create non-root user
RUN useradd -r -u 1001 -g root krrmcp
RUN chown -R krrmcp:root /app
USER 1001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from src.server import KrrMCPServer, ServerConfig; print('healthy')" || exit 1

# Expose port (if needed for health checks)
EXPOSE 8080

# Run server
CMD ["uv", "run", "python", "main.py"]
```

#### Build and Push

```bash
# Build image
docker build -t your-org/krr-mcp:v1.0.0 .
docker build -t your-org/krr-mcp:latest .

# Push to registry
docker push your-org/krr-mcp:v1.0.0
docker push your-org/krr-mcp:latest
```

### Kubernetes Deployment

#### Namespace and RBAC

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: krr-mcp
  labels:
    name: krr-mcp
    security.policy: restricted

---
# serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: krr-mcp-server
  namespace: krr-mcp
automountServiceAccountToken: true

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

# Write access for applying recommendations (restricted)
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets", "statefulsets"]
  verbs: ["patch", "update"]
  resourceNames: [] # Can be restricted to specific resources

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
  namespace: krr-mcp
```

#### Configuration Management

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: krr-mcp-config
  namespace: krr-mcp
data:
  LOG_LEVEL: "INFO"
  CONFIRMATION_TIMEOUT_SECONDS: "300"
  MAX_RESOURCE_CHANGE_PERCENT: "500"
  ROLLBACK_RETENTION_DAYS: "7"
  CRITICAL_WORKLOAD_PATTERNS: "postgres,mysql,redis,controller,operator"
  PRODUCTION_NAMESPACE_PATTERNS: "prod,production,live"
  KRR_STRATEGY: "simple"
  KRR_HISTORY_DURATION: "7d"

---
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: krr-mcp-secrets
  namespace: krr-mcp
type: Opaque
data:
  PROMETHEUS_URL: aHR0cDovL3Byb21ldGhldXMubW9uaXRvcmluZy5zdmMuY2x1c3Rlci5sb2NhbDo5MDkw # base64 encoded
  # Add other sensitive configuration
```

#### Deployment Manifest

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: krr-mcp-server
  namespace: krr-mcp
  labels:
    app: krr-mcp-server
    version: v1.0.0
spec:
  replicas: 2  # For high availability
  selector:
    matchLabels:
      app: krr-mcp-server
  template:
    metadata:
      labels:
        app: krr-mcp-server
        version: v1.0.0
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: krr-mcp-server
      securityContext:
        runAsNonRoot: true
        runAsUser: 1001
        fsGroup: 1001
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: krr-mcp-server
        image: your-org/krr-mcp:v1.0.0
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8080
          name: http
          protocol: TCP
        env:
        - name: KUBERNETES_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        envFrom:
        - configMapRef:
            name: krr-mcp-config
        - secretRef:
            name: krr-mcp-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          runAsNonRoot: true
          runAsUser: 1001
          capabilities:
            drop:
            - ALL
        volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: logs
          mountPath: /app/logs
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
      volumes:
      - name: tmp
        emptyDir: {}
      - name: logs
        emptyDir: {}
      nodeSelector:
        kubernetes.io/arch: amd64
      tolerations:
      - key: "node-role.kubernetes.io/master"
        operator: "Exists"
        effect: "NoSchedule"
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - krr-mcp-server
              topologyKey: kubernetes.io/hostname

---
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: krr-mcp-server
  namespace: krr-mcp
  labels:
    app: krr-mcp-server
spec:
  type: ClusterIP
  ports:
  - port: 8080
    targetPort: http
    protocol: TCP
    name: http
  selector:
    app: krr-mcp-server
```

#### Horizontal Pod Autoscaler

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: krr-mcp-server
  namespace: krr-mcp
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: krr-mcp-server
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 60
```

### Helm Chart

#### Chart Structure

```
krr-mcp-helm/
├── Chart.yaml
├── values.yaml
├── values-prod.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── rbac.yaml
│   ├── hpa.yaml
│   ├── pdb.yaml
│   └── servicemonitor.yaml
└── charts/
```

#### Chart.yaml

```yaml
apiVersion: v2
name: krr-mcp-server
description: A Helm chart for KRR MCP Server
type: application
version: 1.0.0
appVersion: "1.0.0"
keywords:
  - kubernetes
  - optimization
  - mcp
  - krr
home: https://github.com/your-org/krr-mcp
sources:
  - https://github.com/your-org/krr-mcp
maintainers:
  - name: Your Team
    email: team@yourorg.com
dependencies: []
```

#### values.yaml

```yaml
# Default values for krr-mcp-server
replicaCount: 2

image:
  repository: your-org/krr-mcp
  pullPolicy: IfNotPresent
  tag: "v1.0.0"

serviceAccount:
  create: true
  annotations: {}
  name: ""

podAnnotations: {}

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1001
  fsGroup: 1001

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 1001
  capabilities:
    drop:
    - ALL

service:
  type: ClusterIP
  port: 8080

resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

nodeSelector: {}

tolerations: []

affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchExpressions:
          - key: app.kubernetes.io/name
            operator: In
            values:
            - krr-mcp-server
        topologyKey: kubernetes.io/hostname

config:
  logLevel: "INFO"
  confirmationTimeoutSeconds: 300
  maxResourceChangePercent: 500
  rollbackRetentionDays: 7
  criticalWorkloadPatterns: "postgres,mysql,redis,controller,operator"
  productionNamespacePatterns: "prod,production,live"
  krrStrategy: "simple"
  krrHistoryDuration: "7d"

secrets:
  prometheusUrl: "http://prometheus.monitoring.svc.cluster.local:9090"

monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
    namespace: monitoring
    interval: 30s
    scrapeTimeout: 10s
```

#### Installation

```bash
# Add repository
helm repo add krr-mcp https://your-org.github.io/krr-mcp-helm

# Install with default values
helm install krr-mcp krr-mcp/krr-mcp-server \
  --namespace krr-mcp \
  --create-namespace

# Install with production values
helm install krr-mcp krr-mcp/krr-mcp-server \
  --namespace krr-mcp \
  --create-namespace \
  --values values-prod.yaml

# Upgrade
helm upgrade krr-mcp krr-mcp/krr-mcp-server \
  --namespace krr-mcp \
  --values values-prod.yaml
```

## 🖥️ Virtual Machine Deployment

### System Requirements

**Minimum:**
- 2 CPU cores
- 4GB RAM
- 20GB disk space
- Ubuntu 20.04+ or equivalent

**Recommended:**
- 4 CPU cores
- 8GB RAM
- 50GB disk space
- SSD storage for logs

### Installation Script

```bash
#!/bin/bash
# install-krr-mcp.sh

set -euo pipefail

# Configuration
KRR_MCP_VERSION="v1.0.0"
INSTALL_DIR="/opt/krr-mcp"
SERVICE_USER="krrmcp"
LOG_DIR="/var/log/krr-mcp"
CONFIG_DIR="/etc/krr-mcp"

# Create service user
sudo useradd -r -s /bin/false -d ${INSTALL_DIR} ${SERVICE_USER} || true

# Create directories
sudo mkdir -p ${INSTALL_DIR} ${LOG_DIR} ${CONFIG_DIR}
sudo chown ${SERVICE_USER}:${SERVICE_USER} ${INSTALL_DIR} ${LOG_DIR}

# Install system dependencies
sudo apt-get update
sudo apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    curl \
    git \
    jq

# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Install krr
sudo -u ${SERVICE_USER} python3.12 -m pip install --user krr

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sudo -u ${SERVICE_USER} sh

# Clone and install krr-mcp
cd ${INSTALL_DIR}
sudo -u ${SERVICE_USER} git clone https://github.com/your-org/krr-mcp.git .
sudo -u ${SERVICE_USER} ~/.local/bin/uv sync

# Create configuration
sudo tee ${CONFIG_DIR}/config.env << EOF
KUBECONFIG=/home/${SERVICE_USER}/.kube/config
PROMETHEUS_URL=http://prometheus.monitoring.svc.cluster.local:9090
LOG_LEVEL=INFO
CONFIRMATION_TIMEOUT_SECONDS=300
MAX_RESOURCE_CHANGE_PERCENT=500
ROLLBACK_RETENTION_DAYS=7
CRITICAL_WORKLOAD_PATTERNS=postgres,mysql,redis,controller,operator
PRODUCTION_NAMESPACE_PATTERNS=prod,production,live
EOF

sudo chown ${SERVICE_USER}:${SERVICE_USER} ${CONFIG_DIR}/config.env
sudo chmod 600 ${CONFIG_DIR}/config.env

# Create systemd service
sudo tee /etc/systemd/system/krr-mcp.service << EOF
[Unit]
Description=KRR MCP Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=PATH=/home/${SERVICE_USER}/.local/bin:\$PATH
EnvironmentFile=${CONFIG_DIR}/config.env
ExecStart=/home/${SERVICE_USER}/.local/bin/uv run python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=krr-mcp

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${LOG_DIR} /tmp
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
RestrictNamespaces=true
MemoryDenyWriteExecute=true
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable krr-mcp
sudo systemctl start krr-mcp

echo "KRR MCP Server installed successfully!"
echo "Check status with: sudo systemctl status krr-mcp"
echo "View logs with: sudo journalctl -u krr-mcp -f"
```

### Service Management

```bash
# Start service
sudo systemctl start krr-mcp

# Stop service
sudo systemctl stop krr-mcp

# Restart service
sudo systemctl restart krr-mcp

# Check status
sudo systemctl status krr-mcp

# View logs
sudo journalctl -u krr-mcp -f

# Enable auto-start
sudo systemctl enable krr-mcp
```

## 📊 Monitoring and Observability

### Prometheus Metrics

The server exposes metrics for monitoring:

```python
# Custom metrics exposed
krr_mcp_recommendations_total = Counter('krr_mcp_recommendations_total', 'Total recommendations generated')
krr_mcp_confirmations_total = Counter('krr_mcp_confirmations_total', 'Total confirmations requested')  
krr_mcp_executions_total = Counter('krr_mcp_executions_total', 'Total executions performed')
krr_mcp_rollbacks_total = Counter('krr_mcp_rollbacks_total', 'Total rollbacks performed')
krr_mcp_safety_violations_total = Counter('krr_mcp_safety_violations_total', 'Total safety violations blocked')

krr_mcp_execution_duration_seconds = Histogram('krr_mcp_execution_duration_seconds', 'Execution duration')
krr_mcp_confirmation_timeout_seconds = Histogram('krr_mcp_confirmation_timeout_seconds', 'Confirmation timeouts')

krr_mcp_active_tokens = Gauge('krr_mcp_active_tokens', 'Active confirmation tokens')
krr_mcp_component_health = Gauge('krr_mcp_component_health', 'Component health status', ['component'])
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "KRR MCP Server",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(krr_mcp_recommendations_total[5m])",
            "legendFormat": "Recommendations/sec"
          }
        ]
      },
      {
        "title": "Execution Success Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "rate(krr_mcp_executions_total{status=\"success\"}[5m]) / rate(krr_mcp_executions_total[5m]) * 100",
            "legendFormat": "Success Rate %"
          }
        ]
      },
      {
        "title": "Safety Violations",
        "type": "graph",
        "targets": [
          {
            "expr": "increase(krr_mcp_safety_violations_total[1h])",
            "legendFormat": "Violations/hour"
          }
        ]
      }
    ]
  }
}
```

### Alerting Rules

```yaml
# prometheus-alerts.yaml
groups:
  - name: krr-mcp
    rules:
      - alert: KrrMcpServerDown
        expr: up{job="krr-mcp-server"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "KRR MCP Server is down"
          description: "KRR MCP Server has been down for more than 1 minute."

      - alert: KrrMcpHighErrorRate
        expr: rate(krr_mcp_executions_total{status="error"}[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High error rate in KRR MCP Server"
          description: "Error rate is {{ $value }} errors per second."

      - alert: KrrMcpSafetyViolations
        expr: rate(krr_mcp_safety_violations_total[1h]) > 5
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "High number of safety violations"
          description: "{{ $value }} safety violations in the last hour."

      - alert: KrrMcpComponentUnhealthy
        expr: krr_mcp_component_health < 1
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "KRR MCP Server component unhealthy"
          description: "Component {{ $labels.component }} is unhealthy."
```

## 🔒 Security Hardening

### Container Security

```yaml
# security-policy.yaml
apiVersion: v1
kind: Pod
metadata:
  annotations:
    seccomp.security.alpha.kubernetes.io/pod: runtime/default
    container.apparmor.security.beta.kubernetes.io/krr-mcp-server: runtime/default
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1001
    fsGroup: 1001
    seccompProfile:
      type: RuntimeDefault
  containers:
  - name: krr-mcp-server
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      runAsNonRoot: true
      runAsUser: 1001
      capabilities:
        drop:
        - ALL
        add: [] # No additional capabilities
```

### Network Policies

```yaml
# network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: krr-mcp-server
  namespace: krr-mcp
spec:
  podSelector:
    matchLabels:
      app: krr-mcp-server
  policyTypes:
  - Ingress
  - Egress
  ingress:
  # Allow health checks from monitoring
  - from:
    - namespaceSelector:
        matchLabels:
          name: monitoring
    ports:
    - protocol: TCP
      port: 8080
  egress:
  # Allow DNS resolution
  - to: []
    ports:
    - protocol: UDP
      port: 53
  # Allow Kubernetes API access
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: TCP
      port: 443
  # Allow Prometheus access
  - to:
    - namespaceSelector:
        matchLabels:
          name: monitoring
    ports:
    - protocol: TCP
      port: 9090
```

### Pod Security Standards

```yaml
# pod-security-policy.yaml
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: krr-mcp-server
spec:
  privileged: false
  allowPrivilegeEscalation: false
  requiredDropCapabilities:
    - ALL
  volumes:
    - 'configMap'
    - 'emptyDir'
    - 'projected'
    - 'secret'
    - 'downwardAPI'
    - 'persistentVolumeClaim'
  runAsUser:
    rule: 'MustRunAsNonRoot'
  runAsGroup:
    rule: 'MustRunAs'
    ranges:
      - min: 1
        max: 65535
  seLinux:
    rule: 'RunAsAny'
  fsGroup:
    rule: 'RunAsAny'
```

## 🔄 CI/CD Pipeline

### GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy KRR MCP Server

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    
    - name: Install uv
      run: pip install uv
    
    - name: Install dependencies
      run: uv sync
    
    - name: Run tests
      run: uv run python scripts/run_tests.py

  security-scan:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Run security scan
      run: |
        pip install bandit safety
        bandit -r src/
        safety check

  build:
    needs: [test, security-scan]
    runs-on: ubuntu-latest
    outputs:
      image: ${{ steps.image.outputs.image }}
      digest: ${{ steps.build.outputs.digest }}
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
    
    - name: Log in to Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    
    - name: Extract metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
        tags: |
          type=ref,event=branch
          type=ref,event=pr
          type=semver,pattern={{version}}
          type=semver,pattern={{major}}.{{minor}}
    
    - name: Build and push
      id: build
      uses: docker/build-push-action@v5
      with:
        context: .
        platforms: linux/amd64,linux/arm64
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
        cache-from: type=gha
        cache-to: type=gha,mode=max

  deploy-staging:
    if: github.ref == 'refs/heads/main'
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
    - uses: actions/checkout@v4
    
    - name: Deploy to staging
      run: |
        helm upgrade --install krr-mcp-staging ./helm/krr-mcp-server \
          --namespace krr-mcp-staging \
          --create-namespace \
          --set image.tag=${{ github.sha }} \
          --values ./helm/values-staging.yaml

  deploy-production:
    if: startsWith(github.ref, 'refs/tags/v')
    needs: [build, deploy-staging]
    runs-on: ubuntu-latest
    environment: production
    steps:
    - uses: actions/checkout@v4
    
    - name: Deploy to production
      run: |
        helm upgrade --install krr-mcp-prod ./helm/krr-mcp-server \
          --namespace krr-mcp \
          --create-namespace \
          --set image.tag=${{ github.ref_name }} \
          --values ./helm/values-prod.yaml
```

## 📋 Operational Procedures

### Deployment Checklist

**Pre-deployment:**
- [ ] Security scan passed
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Monitoring configured
- [ ] Backup procedures tested
- [ ] Rollback plan prepared
- [ ] Change management approved

**During deployment:**
- [ ] Health checks passing
- [ ] Metrics being collected
- [ ] Logs being generated
- [ ] No error alerts
- [ ] Performance within limits
- [ ] Security policies applied

**Post-deployment:**
- [ ] End-to-end testing
- [ ] Performance validation
- [ ] Security verification
- [ ] Documentation updated
- [ ] Team notification
- [ ] Monitoring review

### Backup and Recovery

```bash
# Backup audit logs
kubectl exec -n krr-mcp deployment/krr-mcp-server -- \
  tar czf - /app/logs | \
  kubectl cp krr-mcp/krr-mcp-server-xxx:/dev/stdin ./backup-$(date +%Y%m%d).tar.gz

# Backup configuration
kubectl get configmap -n krr-mcp krr-mcp-config -o yaml > config-backup.yaml
kubectl get secret -n krr-mcp krr-mcp-secrets -o yaml > secrets-backup.yaml

# Restore from backup
kubectl apply -f config-backup.yaml
kubectl apply -f secrets-backup.yaml
kubectl rollout restart deployment/krr-mcp-server -n krr-mcp
```

### Disaster Recovery

```bash
# Complete cluster recovery
helm install krr-mcp ./helm/krr-mcp-server \
  --namespace krr-mcp \
  --create-namespace \
  --values ./helm/values-prod.yaml

# Restore audit logs
kubectl cp ./backup-20250129.tar.gz krr-mcp/krr-mcp-server-xxx:/tmp/
kubectl exec -n krr-mcp deployment/krr-mcp-server -- \
  tar xzf /tmp/backup-20250129.tar.gz -C /app/
```

## 📚 Related Documentation

- **[Installation Guide](installation.md)** - Prerequisites and setup
- **[User Guide](user-guide.md)** - Usage and best practices
- **[Safety Guide](safety.md)** - Security and safety features
- **[API Reference](api/README.md)** - Technical documentation
- **[Troubleshooting](troubleshooting.md)** - Common issues and solutions

---

**Remember**: Production deployments require careful planning, monitoring, and security considerations. Always test deployments in staging environments first and maintain proper backup and recovery procedures. 