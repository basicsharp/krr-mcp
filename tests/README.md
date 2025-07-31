# Integration Tests

This directory contains integration tests for the KRR MCP Server that require a real Kubernetes cluster.

## Test Categories

### Unit Tests
- Fast tests that don't require external dependencies
- Use mocking for external services
- Run with: `uv run pytest tests/test_*.py -v`

### Integration Tests
- Require a real Kubernetes cluster (kind)
- Test actual kubectl operations
- Run with: `uv run pytest tests/test_integration_cluster.py -v`

## Setting Up Integration Tests

### Prerequisites
- Docker installed and running
- `kind` CLI tool installed
- `kubectl` CLI tool installed

### Cluster Setup
```bash
# Set up test cluster
python tests/cluster_manager.py setup

# Check cluster status
python tests/cluster_manager.py status

# Recreate cluster (if needed)
python tests/cluster_manager.py recreate

# Clean up cluster
python tests/cluster_manager.py teardown
```

### Running Integration Tests

```bash
# Run all integration tests
uv run pytest tests/test_integration_cluster.py -v

# Run specific integration test
uv run pytest tests/test_integration_cluster.py::TestClusterIntegration::test_cluster_connectivity -v

# Run with coverage
uv run pytest tests/test_integration_cluster.py --cov=src --cov-report=html
```

## Test Cluster Details

- **Cluster Name**: `krr-test`
- **Context**: `kind-krr-test`
- **Namespaces**: `test-app`, `staging-app`, `production-app`
- **Test Workloads**: Multiple deployments with different resource configurations

## Test Cases Covered

1. **Cluster Connectivity**: Verify kubectl executor can connect to cluster
2. **Resource Updates**: Test actual resource changes via kubectl
3. **Staged Rollout**: Test multi-namespace deployment ordering
4. **Post-Execution Validation**: Test resource verification after changes
5. **Rollback Functionality**: Test transaction rollback capabilities
6. **Error Handling**: Test graceful handling of invalid resources
7. **Dry-Run Operations**: Test dry-run mode execution

## Safety Features

All integration tests are designed with safety in mind:
- Most tests use dry-run mode to avoid actual cluster changes
- Test workloads are isolated in dedicated namespaces
- Rollback capabilities are tested but not actually executed
- Cluster state is preserved between test runs for debugging

## Troubleshooting

### Cluster Not Starting
```bash
# Check Docker is running
docker ps

# Recreate cluster
python tests/cluster_manager.py recreate
```

### Tests Failing
```bash
# Check cluster status
kubectl get nodes --context kind-krr-test

# Check test workloads
kubectl get pods --all-namespaces --context kind-krr-test

# View cluster logs
kind export logs --name krr-test
```

### Cleanup
```bash
# Remove test cluster
python tests/cluster_manager.py teardown

# Clean up Docker resources
docker system prune -f
```

## Performance

Integration tests typically run in:
- Setup time: ~60 seconds (first time)
- Test execution: ~1-2 seconds per test
- Cleanup time: ~10 seconds

The cluster is left running between test sessions to speed up subsequent runs.
