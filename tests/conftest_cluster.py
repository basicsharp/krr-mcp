"""
Shared fixtures for cluster integration tests.

This module provides cluster lifecycle management for integration tests.
"""

import subprocess
from pathlib import Path

import pytest

from .cluster_manager import ClusterManager


@pytest.fixture(scope="session", autouse=True)
def cluster_lifecycle():
    """Manage cluster lifecycle for all integration tests."""
    manager = ClusterManager()

    # Set up cluster at start of session
    if not manager.cluster_exists() or not manager.is_cluster_ready():
        print("\n🚀 Setting up test cluster for integration tests...")
        success = manager.setup_cluster()
        if not success:
            pytest.skip("Failed to set up test cluster")
    else:
        print("\n✅ Using existing test cluster")

    yield manager

    # Note: We don't automatically tear down the cluster to allow for debugging
    # Use `python tests/cluster_manager.py teardown` to manually clean up
    print(
        "\n💡 Test cluster left running for debugging. Use 'python tests/cluster_manager.py teardown' to clean up."
    )


@pytest.fixture
def cluster_manager(cluster_lifecycle):
    """Provide cluster manager instance to tests."""
    return cluster_lifecycle


# Add a marker for tests that require a real cluster
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "cluster: mark test as requiring a real Kubernetes cluster"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle cluster requirements."""
    # Check if we can connect to the test cluster
    try:
        result = subprocess.run(
            ["kubectl", "get", "nodes", "--context", "kind-krr-test"],
            capture_output=True,
            timeout=10,
        )
        cluster_available = result.returncode == 0
    except Exception:
        cluster_available = False

    if not cluster_available:
        # Skip cluster tests if cluster is not available
        skip_cluster = pytest.mark.skip(reason="Test cluster not available")
        for item in items:
            if "test_integration_cluster" in str(item.fspath):
                item.add_marker(skip_cluster)
