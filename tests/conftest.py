"""Pytest configuration and shared fixtures for KRR MCP Server tests."""

import asyncio
from pathlib import Path
from typing import AsyncGenerator, Dict, Generator
from unittest.mock import AsyncMock, Mock

import pytest
import structlog
from fastmcp import FastMCP

from src.server import KrrMCPServer, ServerConfig


@pytest.fixture(scope="session")
def event_loop_policy():
    """Set the event loop policy for the test session."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def test_config() -> ServerConfig:
    """Create a test configuration with safe defaults."""
    return ServerConfig(
        kubeconfig="/tmp/test-kubeconfig",
        kubernetes_context="test-context",
        prometheus_url="http://localhost:9090",
        krr_strategy="simple",
        krr_history_duration="1d",
        confirmation_timeout_seconds=60,
        max_resource_change_percent=200,
        rollback_retention_days=1,
        development_mode=True,
        mock_krr_responses=True,
        mock_kubectl_commands=True,
    )


@pytest.fixture
async def test_server(test_config: ServerConfig) -> AsyncGenerator[KrrMCPServer, None]:
    """Create a test server instance."""
    server = KrrMCPServer(test_config)
    
    # Mock the MCP server to avoid actual network operations
    server.mcp = Mock(spec=FastMCP)
    server.mcp.run = AsyncMock()
    
    yield server
    
    # Clean up
    await server.stop()


@pytest.fixture
def mock_krr_response() -> Dict:
    """Mock krr command response."""
    return {
        "recommendations": [
            {
                "object": {
                    "kind": "Deployment",
                    "namespace": "default",
                    "name": "test-app",
                },
                "recommendations": {
                    "requests": {
                        "cpu": "250m",
                        "memory": "256Mi",
                    },
                    "limits": {
                        "cpu": "500m", 
                        "memory": "512Mi",
                    }
                },
                "current": {
                    "requests": {
                        "cpu": "100m",
                        "memory": "128Mi",
                    },
                    "limits": {
                        "cpu": "200m",
                        "memory": "256Mi", 
                    }
                }
            }
        ],
        "metadata": {
            "strategy": "simple",
            "timestamp": "2025-01-29T00:00:00Z",
            "cluster": "test-cluster",
        }
    }


@pytest.fixture
def mock_kubectl_dry_run() -> Dict:
    """Mock kubectl dry-run response."""
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "test-app",
            "namespace": "default",
        },
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "resources": {
                                "requests": {
                                    "cpu": "250m",
                                    "memory": "256Mi",
                                },
                                "limits": {
                                    "cpu": "500m",
                                    "memory": "512Mi",
                                }
                            }
                        }
                    ]
                }
            }
        }
    }


@pytest.fixture
def dangerous_recommendations() -> Dict:
    """Create recommendations that should trigger safety warnings."""
    return {
        "recommendations": [
            {
                "object": {
                    "kind": "Deployment",
                    "namespace": "production",
                    "name": "critical-service",
                },
                "recommendations": {
                    "requests": {
                        "cpu": "10000m",  # 10x increase - should trigger safety check
                        "memory": "10Gi",  # Large increase
                    }
                },
                "current": {
                    "requests": {
                        "cpu": "1000m",
                        "memory": "1Gi",
                    }
                }
            }
        ]
    }


@pytest.fixture
def sample_confirmation_token() -> str:
    """Generate a sample confirmation token for testing."""
    return "test-confirmation-token-12345"


@pytest.fixture
def caplog_structured(caplog):
    """Fixture for capturing structured logs."""
    # Configure structlog to use the standard library logger for tests
    structlog.configure(
        processors=[
            structlog.testing.LogCapture(),
        ],
        logger_factory=structlog.testing.CapturingLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    return caplog


class MockAsyncProcess:
    """Mock async subprocess for testing external commands."""
    
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout.encode() if isinstance(stdout, str) else stdout
        self.stderr = stderr.encode() if isinstance(stderr, str) else stderr
        self.returncode = returncode
    
    async def communicate(self):
        """Mock communicate method."""
        return self.stdout, self.stderr
    
    async def wait(self):
        """Mock wait method."""
        return self.returncode


@pytest.fixture
def mock_subprocess():
    """Mock asyncio subprocess for testing external commands."""
    return MockAsyncProcess


# Safety test scenarios
@pytest.fixture
def bypass_attempt_scenarios():
    """Scenarios that attempt to bypass safety checks."""
    return [
        {
            "name": "direct_execution_without_confirmation",
            "description": "Attempt to execute without confirmation token",
            "expected_result": "rejection",
        },
        {
            "name": "expired_confirmation_token",
            "description": "Use expired confirmation token",
            "expected_result": "rejection",
        },
        {
            "name": "modified_confirmation_data",
            "description": "Attempt with modified confirmation data",
            "expected_result": "rejection",
        },
        {
            "name": "replay_attack",
            "description": "Reuse the same confirmation token",
            "expected_result": "rejection",
        },
    ]


@pytest.fixture
def edge_case_scenarios():
    """Edge case scenarios for testing robustness."""
    return [
        {
            "name": "empty_recommendations",
            "recommendations": [],
            "expected_result": "no_changes",
        },
        {
            "name": "invalid_resource_spec",
            "recommendations": [{"invalid": "data"}],
            "expected_result": "validation_error",
        },
        {
            "name": "network_interruption",
            "simulate": "network_failure",
            "expected_result": "graceful_failure",
        },
        {
            "name": "kubernetes_api_error",
            "simulate": "k8s_api_error",
            "expected_result": "error_recovery",
        },
    ]