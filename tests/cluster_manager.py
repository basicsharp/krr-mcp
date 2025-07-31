#!/usr/bin/env python3
"""
Test cluster management script for KRR MCP Server integration tests.

Provides commands to setup, teardown, and manage test clusters.
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


class ClusterManager:
    """Manages test cluster lifecycle for integration tests."""

    def __init__(self, cluster_name: str = "krr-test"):
        self.cluster_name = cluster_name
        self.context_name = f"kind-{cluster_name}"
        self.config_path = Path(__file__).parent / "kind-config.yaml"
        self.workloads_path = Path(__file__).parent / "test-workloads.yaml"

    def cluster_exists(self) -> bool:
        """Check if the test cluster exists."""
        try:
            result = subprocess.run(
                ["kind", "get", "clusters"], capture_output=True, text=True, timeout=10
            )
            return self.cluster_name in result.stdout
        except Exception:
            return False

    def is_cluster_ready(self) -> bool:
        """Check if cluster is ready for testing."""
        try:
            result = subprocess.run(
                ["kubectl", "get", "nodes", "--context", self.context_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False

            # Check if all nodes are ready
            lines = result.stdout.strip().split("\n")[1:]  # Skip header
            for line in lines:
                if "Ready" not in line:
                    return False
            return True
        except Exception:
            return False

    def create_cluster(self, wait_timeout: int = 300) -> bool:
        """Create the test cluster."""
        print(f"Creating test cluster '{self.cluster_name}'...")

        try:
            cmd = [
                "kind",
                "create",
                "cluster",
                "--config",
                str(self.config_path),
                "--wait",
                f"{wait_timeout}s",
            ]

            result = subprocess.run(cmd, timeout=wait_timeout + 60)

            if result.returncode != 0:
                print(f"Failed to create cluster (exit code: {result.returncode})")
                return False

            print("✅ Cluster created successfully")
            return True

        except subprocess.TimeoutExpired:
            print("❌ Cluster creation timed out")
            return False
        except Exception as e:
            print(f"❌ Error creating cluster: {e}")
            return False

    def delete_cluster(self) -> bool:
        """Delete the test cluster."""
        print(f"Deleting test cluster '{self.cluster_name}'...")

        try:
            result = subprocess.run(
                ["kind", "delete", "cluster", "--name", self.cluster_name], timeout=60
            )

            if result.returncode == 0:
                print("✅ Cluster deleted successfully")
                return True
            else:
                print(f"Failed to delete cluster (exit code: {result.returncode})")
                return False

        except Exception as e:
            print(f"❌ Error deleting cluster: {e}")
            return False

    def deploy_test_workloads(self) -> bool:
        """Deploy test workloads to the cluster."""
        print("Deploying test workloads...")

        try:
            # Apply workloads
            result = subprocess.run(
                [
                    "kubectl",
                    "apply",
                    "-f",
                    str(self.workloads_path),
                    "--context",
                    self.context_name,
                ],
                timeout=60,
            )

            if result.returncode != 0:
                print(f"Failed to deploy workloads (exit code: {result.returncode})")
                return False

            # Wait for deployments to be ready
            print("Waiting for deployments to be ready...")
            result = subprocess.run(
                [
                    "kubectl",
                    "wait",
                    "--for=condition=available",
                    "--timeout=120s",
                    "deployment",
                    "--all",
                    "--all-namespaces",
                    "--context",
                    self.context_name,
                ],
                timeout=150,
            )

            if result.returncode != 0:
                print("⚠️  Some deployments may not be ready, but continuing...")
            else:
                print("✅ All deployments are ready")

            return True

        except Exception as e:
            print(f"❌ Error deploying workloads: {e}")
            return False

    def setup_cluster(self, force: bool = False) -> bool:
        """Set up the complete test environment."""
        if self.cluster_exists() and not force:
            if self.is_cluster_ready():
                print(f"✅ Cluster '{self.cluster_name}' already exists and is ready")
                return True
            else:
                print(f"⚠️  Cluster exists but not ready, recreating...")
                self.delete_cluster()
        elif self.cluster_exists() and force:
            print("🔄 Force recreating cluster...")
            self.delete_cluster()

        # Create cluster
        if not self.create_cluster():
            return False

        # Wait a bit for cluster to stabilize
        print("Waiting for cluster to stabilize...")
        time.sleep(10)

        # Deploy test workloads
        if not self.deploy_test_workloads():
            return False

        print("🎉 Test cluster setup complete!")
        return True

    def teardown_cluster(self) -> bool:
        """Tear down the test environment."""
        if not self.cluster_exists():
            print(f"Cluster '{self.cluster_name}' does not exist")
            return True

        return self.delete_cluster()

    def status(self) -> None:
        """Show cluster status."""
        print(f"Cluster: {self.cluster_name}")
        print(f"Context: {self.context_name}")
        print(f"Exists: {'✅' if self.cluster_exists() else '❌'}")
        print(f"Ready: {'✅' if self.is_cluster_ready() else '❌'}")

        if self.cluster_exists():
            try:
                # Show nodes
                result = subprocess.run(
                    ["kubectl", "get", "nodes", "--context", self.context_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    print("\nNodes:")
                    print(result.stdout)

                # Show test workloads
                result = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "pods",
                        "--all-namespaces",
                        "--context",
                        self.context_name,
                        "-l",
                        "app",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0 and result.stdout.strip():
                    print("Test Workloads:")
                    print(result.stdout)

            except Exception as e:
                print(f"Error getting status: {e}")


def main():
    """Main CLI interface."""
    if len(sys.argv) < 2:
        print("Usage: python cluster_manager.py <command>")
        print("Commands:")
        print("  setup [--force]  - Set up test cluster")
        print("  teardown         - Tear down test cluster")
        print("  status           - Show cluster status")
        print("  recreate         - Force recreate cluster")
        sys.exit(1)

    manager = ClusterManager()
    command = sys.argv[1]

    if command == "setup":
        force = "--force" in sys.argv
        success = manager.setup_cluster(force=force)
        sys.exit(0 if success else 1)

    elif command == "teardown":
        success = manager.teardown_cluster()
        sys.exit(0 if success else 1)

    elif command == "status":
        manager.status()
        sys.exit(0)

    elif command == "recreate":
        success = manager.setup_cluster(force=True)
        sys.exit(0 if success else 1)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
