"""Additional coverage tests for KrrClient.

This module provides comprehensive test coverage for KrrClient methods
and functionality to reach the 90% coverage requirement.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.recommender.krr_client import KrrClient
from src.recommender.models import (
    CachedScanResult,
    KrrError,
    KrrExecutionError,
    KrrNotFoundError,
    KrrRecommendation,
    KrrScanResult,
    KrrStrategy,
    KrrVersionError,
    KubernetesContextError,
    KubernetesObject,
    PrometheusConnectionError,
    RecommendationSeverity,
    ResourceValue,
)


class TestKrrClientCoverage:
    """Additional coverage tests for KrrClient methods."""

    @pytest.fixture
    async def client(self):
        """Create test client instance."""
        return KrrClient(
            kubeconfig_path="/test/kubeconfig",
            kubernetes_context="test-context",
            prometheus_url="http://test-prometheus:9090",
            cache_ttl_seconds=300,
            mock_responses=False,
        )

    @pytest.fixture
    async def mock_client(self):
        """Create mock client instance."""
        return KrrClient(mock_responses=True)

    # Test _verify_krr_availability method coverage
    @pytest.mark.asyncio
    async def test_verify_krr_availability_not_found(self, client):
        """Test krr not found in PATH."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(KrrNotFoundError):
                await client._verify_krr_availability()

    @pytest.mark.asyncio
    async def test_verify_krr_availability_version_error(self, client):
        """Test krr availability check with version error."""
        with patch("shutil.which", return_value="/usr/bin/krr"):
            with patch.object(
                client,
                "_check_krr_version",
                side_effect=KrrVersionError("Version error", None, "1.7.0"),
            ):
                with pytest.raises(KrrVersionError):
                    await client._verify_krr_availability()

    @pytest.mark.asyncio
    async def test_verify_krr_availability_general_error(self, client):
        """Test krr availability check with general error."""
        with patch("shutil.which", return_value="/usr/bin/krr"):
            with patch.object(
                client, "_check_krr_version", side_effect=Exception("General error")
            ):
                with pytest.raises(Exception):
                    await client._verify_krr_availability()

    # Test _check_krr_version method coverage
    @pytest.mark.asyncio
    async def test_check_krr_version_timeout(self, client):
        """Test krr version check timeout."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError
            mock_process.kill = AsyncMock()
            mock_process.wait = AsyncMock()
            mock_subprocess.return_value = mock_process

            with pytest.raises(KrrVersionError) as exc:
                await client._check_krr_version()
            assert "timed out after 30 seconds" in str(exc.value)

    @pytest.mark.asyncio
    async def test_check_krr_version_error_return_code(self, client):
        """Test krr version check error return code."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Error message")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            with pytest.raises(KrrVersionError) as exc:
                await client._check_krr_version()
            assert "Failed to get krr version" in str(exc.value)

    @pytest.mark.asyncio
    async def test_check_krr_version_parse_error(self, client):
        """Test krr version check with unparseable output."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"invalid output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with pytest.raises(KrrVersionError) as exc:
                await client._check_krr_version()
            assert "Cannot parse krr version" in str(exc.value)

    @pytest.mark.asyncio
    async def test_check_krr_version_incompatible(self, client):
        """Test krr version check with incompatible version."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"krr version 1.6.0", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with pytest.raises(KrrVersionError) as exc:
                await client._check_krr_version()
            assert "not compatible" in str(exc.value)

    @pytest.mark.asyncio
    async def test_check_krr_version_success(self, client):
        """Test successful krr version check."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"krr version 1.8.0", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            version = await client._check_krr_version()
            assert version == "1.8.0"

    @pytest.mark.asyncio
    async def test_check_krr_version_generic_timeout_error(self, client):
        """Test krr version check with generic timeout error."""
        with patch("asyncio.create_subprocess_exec", side_effect=asyncio.TimeoutError):
            with pytest.raises(KrrVersionError) as exc:
                await client._check_krr_version()
            assert "Timeout while checking" in str(exc.value)

    @pytest.mark.asyncio
    async def test_check_krr_version_generic_error(self, client):
        """Test krr version check with generic error that's not KrrVersionError."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=OSError("System error")
        ):
            with pytest.raises(KrrVersionError) as exc:
                await client._check_krr_version()
            assert "Error checking krr version" in str(exc.value)

    # Test _is_version_compatible method coverage
    def test_is_version_compatible_edge_cases(self, client):
        """Test version compatibility checking edge cases."""
        # Test malformed versions
        assert (
            client._is_version_compatible("invalid", "1.7.0") is True
        )  # Assumes compatible
        assert (
            client._is_version_compatible("1.7.0", "invalid") is True
        )  # Assumes compatible

        # Test different length versions
        assert client._is_version_compatible("1.8", "1.7.0") is True
        assert client._is_version_compatible("1.7.0", "1.8") is False

    # Test _build_krr_command method coverage
    def test_build_krr_command_all_options(self, client):
        """Test building krr command with all options."""
        command = client._build_krr_command(
            namespace="test-namespace",
            strategy=KrrStrategy.SIMPLE_LIMIT,
            history_duration="14d",
        )

        assert command[0] == "krr"
        assert command[1] == "simple-limit"
        assert "--history-duration" in command
        assert "14d" in command
        assert "--prometheus-url" in command
        assert "http://test-prometheus:9090" in command
        assert "--formatter" in command
        assert "json" in command
        assert "--kubeconfig" in command
        assert "/test/kubeconfig" in command
        assert "--context" in command
        assert "test-context" in command
        assert "--namespace" in command
        assert "test-namespace" in command

    def test_build_krr_command_minimal(self, client):
        """Test building krr command with minimal options."""
        # Create client without kubeconfig and context
        minimal_client = KrrClient()
        command = minimal_client._build_krr_command()

        assert command[0] == "krr"
        assert command[1] == "simple"  # Default strategy
        assert "--history-duration" in command
        assert "7d" in command  # Default history
        assert "--prometheus-url" in command
        assert "http://localhost:9090" in command  # Default prometheus
        assert "--formatter" in command
        assert "json" in command
        # Should not contain kubeconfig or context options
        assert "--kubeconfig" not in command
        assert "--context" not in command

    # Test _execute_krr_command method coverage
    @pytest.mark.asyncio
    async def test_execute_krr_command_timeout(self, client):
        """Test krr command execution timeout."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError
            mock_process.kill = AsyncMock()
            mock_process.wait = AsyncMock()
            mock_subprocess.return_value = mock_process

            with pytest.raises(KrrExecutionError) as exc:
                await client._execute_krr_command(["krr", "simple"], timeout=1)
            assert "timed out after 1 seconds" in str(exc.value)

    @pytest.mark.asyncio
    async def test_execute_krr_command_prometheus_error(self, client):
        """Test krr command execution with Prometheus connection error."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                b"",
                b"prometheus connection refused",
            )
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            with pytest.raises(PrometheusConnectionError) as exc:
                await client._execute_krr_command(["krr", "simple"])
            assert "Failed to connect to Prometheus" in str(exc.value)

    @pytest.mark.asyncio
    async def test_execute_krr_command_kubernetes_context_error(self, client):
        """Test krr command execution with Kubernetes context error."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                b"",
                b"context not found in kubeconfig",
            )
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            with pytest.raises(KubernetesContextError) as exc:
                await client._execute_krr_command(["krr", "simple"])
            assert "Kubernetes context error" in str(exc.value)

    @pytest.mark.asyncio
    async def test_execute_krr_command_generic_error(self, client):
        """Test krr command execution with generic error."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"some other error")
            mock_process.returncode = 2
            mock_subprocess.return_value = mock_process

            with pytest.raises(KrrExecutionError) as exc:
                await client._execute_krr_command(["krr", "simple"])
            assert "krr command failed" in str(exc.value)

    @pytest.mark.asyncio
    async def test_execute_krr_command_no_output(self, client):
        """Test krr command execution with no output."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with pytest.raises(KrrExecutionError) as exc:
                await client._execute_krr_command(["krr", "simple"])
            assert "produced no output" in str(exc.value)

    @pytest.mark.asyncio
    async def test_execute_krr_command_unexpected_error(self, client):
        """Test krr command execution with unexpected error."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=OSError("System error")
        ):
            with pytest.raises(KrrExecutionError) as exc:
                await client._execute_krr_command(["krr", "simple"])
            assert "Unexpected error executing krr" in str(exc.value)

    # Test _parse_krr_output method coverage
    @pytest.mark.asyncio
    async def test_parse_krr_output_json_decode_error(self, client):
        """Test krr output parsing with JSON decode error."""
        with pytest.raises(KrrExecutionError) as exc:
            await client._parse_krr_output(
                "invalid json", KrrStrategy.SIMPLE, "7d", 2.5
            )
        assert "Failed to parse krr JSON output" in str(exc.value)

    @pytest.mark.asyncio
    async def test_parse_krr_output_general_error(self, client):
        """Test krr output parsing with general error."""
        # Mock _parse_single_recommendation to raise an error
        with patch.object(
            client,
            "_parse_single_recommendation",
            side_effect=ValueError("Parse error"),
        ):
            raw_output = json.dumps(
                {"recommendations": [{"test": "data"}], "metadata": {}}
            )

            # Should handle the error and continue - this tests the exception handling in the loop
            result = await client._parse_krr_output(
                raw_output, KrrStrategy.SIMPLE, "7d", 2.5
            )
            assert (
                len(result.recommendations) == 0
            )  # Failed recommendation should be skipped

    @pytest.mark.asyncio
    async def test_parse_krr_output_success(self, client):
        """Test successful krr output parsing."""
        raw_output = json.dumps(
            {
                "recommendations": [
                    {
                        "object": {
                            "kind": "Deployment",
                            "name": "test",
                            "namespace": "default",
                        },
                        "current": {
                            "requests": {"cpu": "100m", "memory": "128Mi"},
                            "limits": {"cpu": "200m", "memory": "256Mi"},
                        },
                        "recommendations": {
                            "requests": {"cpu": "150m", "memory": "192Mi"},
                            "limits": {"cpu": "300m", "memory": "384Mi"},
                        },
                    }
                ],
                "metadata": {"namespaces": ["default"], "krr_version": "1.8.0"},
            }
        )

        result = await client._parse_krr_output(
            raw_output, KrrStrategy.SIMPLE, "7d", 2.5
        )
        assert isinstance(result, KrrScanResult)
        assert len(result.recommendations) == 1
        assert result.strategy == KrrStrategy.SIMPLE
        assert result.analysis_period == "7d"
        assert result.scan_duration_seconds == 2.5

    # Test _parse_single_recommendation method coverage
    def test_parse_single_recommendation_full(self, client):
        """Test parsing single recommendation with full data."""
        raw_rec = {
            "object": {"kind": "Deployment", "name": "web-app", "namespace": "prod"},
            "current": {
                "requests": {"cpu": "500m", "memory": "512Mi"},
                "limits": {"cpu": "1000m", "memory": "1Gi"},
            },
            "recommendations": {
                "requests": {"cpu": "750m", "memory": "768Mi"},
                "limits": {"cpu": "1500m", "memory": "1.5Gi"},
            },
            "potential_savings": 25.5,
            "confidence_score": 0.92,
            "analysis_period": "14d",
            "cpu_usage_percentile": 95.0,
            "memory_usage_percentile": 90.0,
        }

        result = client._parse_single_recommendation(raw_rec)
        assert isinstance(result, KrrRecommendation)
        assert result.object.kind == "Deployment"
        assert result.object.name == "web-app"
        assert result.object.namespace == "prod"
        assert result.current_requests.cpu == "500m"
        assert result.current_requests.memory == "512Mi"
        assert result.potential_savings == 25.5
        assert result.confidence_score == 0.92

    def test_parse_single_recommendation_minimal(self, client):
        """Test parsing single recommendation with minimal data."""
        raw_rec = {
            "object": {"kind": "Pod", "name": "test-pod"},
            "current": {},
            "recommendations": {},
        }

        result = client._parse_single_recommendation(raw_rec)
        assert isinstance(result, KrrRecommendation)
        assert result.object.kind == "Pod"
        assert result.object.name == "test-pod"
        assert result.object.namespace == "default"  # Default value
        assert result.severity == RecommendationSeverity.MEDIUM  # Default

    # Test cache methods coverage
    def test_generate_cache_key(self, client):
        """Test cache key generation."""
        key = client._generate_cache_key("test-ns", KrrStrategy.SIMPLE_LIMIT, "14d")
        assert "cluster:test-context" in key
        assert "namespace:test-ns" in key
        assert "strategy:simple-limit" in key
        assert "history:14d" in key
        assert "prometheus:http://test-prometheus:9090" in key

    def test_generate_cache_key_none_namespace(self, client):
        """Test cache key generation with None namespace."""
        key = client._generate_cache_key(None, KrrStrategy.SIMPLE, "7d")
        assert "namespace:all" in key

    def test_cache_operations(self, client):
        """Test cache storage and retrieval operations."""
        # Create a test scan result
        scan_result = KrrScanResult(
            scan_id="test-scan",
            strategy=KrrStrategy.SIMPLE,
            cluster_context="test",
            prometheus_url="http://localhost:9090",
            namespaces_scanned=["default"],
            analysis_period="7d",
            recommendations=[],
            total_recommendations=0,
            potential_total_savings=0.0,
            scan_duration_seconds=1.5,
            krr_version="1.8.0",
        )

        cache_key = "test-cache-key"

        # Test cache miss
        result = client._get_cached_result(cache_key)
        assert result is None

        # Test cache storage
        client._cache_scan_result(cache_key, scan_result)

        # Test cache hit
        cached = client._get_cached_result(cache_key)
        assert cached is not None
        assert cached.scan_result.scan_id == "test-scan"

    def test_cache_expiration(self, client):
        """Test cache expiration handling."""
        # Create expired cached result
        scan_result = KrrScanResult(
            scan_id="expired-scan",
            strategy=KrrStrategy.SIMPLE,
            cluster_context="test",
            prometheus_url="http://localhost:9090",
            namespaces_scanned=["default"],
            analysis_period="7d",
            recommendations=[],
            total_recommendations=0,
            potential_total_savings=0.0,
            scan_duration_seconds=1.5,
            krr_version="1.8.0",
        )

        # Create expired cached result manually
        expired_cached = CachedScanResult(
            cache_key="expired-key", scan_result=scan_result, ttl_seconds=1
        )
        # Manually set expired timestamp
        expired_cached.cached_at = datetime.now(timezone.utc) - timedelta(seconds=2)

        client._cache["expired-key"] = expired_cached

        # Should return None for expired entry and remove it
        result = client._get_cached_result("expired-key")
        assert result is None
        assert "expired-key" not in client._cache

    def test_cleanup_expired_cache(self, client):
        """Test cleanup of expired cache entries."""
        # Add some expired entries manually
        for i in range(3):
            scan_result = KrrScanResult(
                scan_id=f"scan-{i}",
                strategy=KrrStrategy.SIMPLE,
                cluster_context="test",
                prometheus_url="http://localhost:9090",
                namespaces_scanned=["default"],
                analysis_period="7d",
                recommendations=[],
                total_recommendations=0,
                potential_total_savings=0.0,
                scan_duration_seconds=1.5,
                krr_version="1.8.0",
            )

            expired_cached = CachedScanResult(
                cache_key=f"expired-key-{i}", scan_result=scan_result, ttl_seconds=1
            )
            expired_cached.cached_at = datetime.now(timezone.utc) - timedelta(seconds=2)
            client._cache[f"expired-key-{i}"] = expired_cached

        # Clean up expired entries
        removed_count = client.cleanup_expired_cache()
        assert removed_count == 3
        assert len(client._cache) == 0

    # Test scan_recommendations with mock responses
    @pytest.mark.asyncio
    async def test_generate_mock_scan_result(self, mock_client):
        """Test mock scan result generation."""
        result = await mock_client._generate_mock_scan_result(
            "default", KrrStrategy.SIMPLE, "7d"
        )

        assert isinstance(result, KrrScanResult)
        assert result.strategy == KrrStrategy.SIMPLE
        assert result.cluster_context == "mock-cluster"
        assert result.analysis_period == "7d"
        assert (
            len(result.recommendations) == 1
        )  # Should filter to default namespace only
        assert result.recommendations[0].object.namespace == "default"

    @pytest.mark.asyncio
    async def test_generate_mock_scan_result_all_namespaces(self, mock_client):
        """Test mock scan result generation for all namespaces."""
        result = await mock_client._generate_mock_scan_result(
            None, KrrStrategy.SIMPLE, "7d"
        )

        assert len(result.recommendations) == 2  # Both mock recommendations
        assert len(result.namespaces_scanned) == 2

    # Test scan_recommendations method edge cases
    @pytest.mark.asyncio
    async def test_scan_recommendations_verification_on_first_use(self, client):
        """Test that krr verification happens on first non-mock use."""
        assert not client._krr_verified

        with patch.object(client, "_verify_krr_availability") as mock_verify:
            with patch.object(
                client,
                "_execute_krr_command",
                return_value='{"recommendations":[],"metadata":{}}',
            ):
                with patch.object(client, "_parse_krr_output") as mock_parse:
                    mock_parse.return_value = KrrScanResult(
                        scan_id="test",
                        strategy=KrrStrategy.SIMPLE,
                        cluster_context="test",
                        prometheus_url="http://localhost:9090",
                        namespaces_scanned=[],
                        analysis_period="7d",
                        recommendations=[],
                        total_recommendations=0,
                        potential_total_savings=0.0,
                        scan_duration_seconds=1.0,
                        krr_version="1.8.0",
                    )

                    await client.scan_recommendations()

                    mock_verify.assert_called_once()
                    assert client._krr_verified

    @pytest.mark.asyncio
    async def test_scan_recommendations_cache_hit(self, client):
        """Test scan_recommendations with cache hit."""
        # Skip verification to avoid actual krr execution
        client._krr_verified = True

        # Pre-populate cache
        cached_result = KrrScanResult(
            scan_id="cached-scan",
            strategy=KrrStrategy.SIMPLE,
            cluster_context="test",
            prometheus_url="http://localhost:9090",
            namespaces_scanned=["default"],
            analysis_period="7d",
            recommendations=[],
            total_recommendations=0,
            potential_total_savings=0.0,
            scan_duration_seconds=1.0,
            krr_version="1.8.0",
        )

        cache_key = client._generate_cache_key("default", KrrStrategy.SIMPLE, "7d")
        client._cache_scan_result(cache_key, cached_result)

        # Should return cached result without executing krr
        with patch.object(client, "_execute_krr_command") as mock_execute:
            result = await client.scan_recommendations(namespace="default")

            mock_execute.assert_not_called()
            assert result.scan_id == "cached-scan"

    @pytest.mark.asyncio
    async def test_scan_recommendations_execution_error_handling(self, client):
        """Test scan_recommendations error handling during execution."""
        client._krr_verified = True  # Skip verification

        with patch.object(
            client, "_execute_krr_command", side_effect=OSError("System error")
        ):
            with pytest.raises(KrrExecutionError) as exc:
                await client.scan_recommendations(use_cache=False)
            assert "Unexpected error during krr scan" in str(exc.value)

    # Test filter_recommendations method
    def test_filter_recommendations(self, client):
        """Test recommendation filtering."""
        # Create a mock scan result with filter method
        scan_result = MagicMock()
        scan_result.filter_recommendations.return_value = []

        filter_criteria = MagicMock()
        result = client.filter_recommendations(scan_result, filter_criteria)

        scan_result.filter_recommendations.assert_called_once_with(filter_criteria)
        assert result == []
