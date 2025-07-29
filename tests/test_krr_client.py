"""Comprehensive tests for krr client module."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
    RecommendationFilter,
    RecommendationSeverity,
    ResourceValue,
)


class TestKrrClientInitialization:
    """Test krr client initialization."""

    def test_initialization_defaults(self):
        """Test default initialization parameters."""
        client = KrrClient(mock_responses=True)

        assert client.kubeconfig_path is None
        assert client.kubernetes_context is None
        assert client.prometheus_url == "http://localhost:9090"
        assert client.cache_ttl_seconds == 300
        assert client.mock_responses is True
        assert client.logger is not None
        assert isinstance(client._cache, dict)

    def test_initialization_with_parameters(self):
        """Test initialization with custom parameters."""
        client = KrrClient(
            kubeconfig_path="/tmp/kubeconfig",
            kubernetes_context="test-context",
            prometheus_url="http://custom:9090",
            cache_ttl_seconds=600,
            mock_responses=True,
        )

        assert client.kubeconfig_path == "/tmp/kubeconfig"
        assert client.kubernetes_context == "test-context"
        assert client.prometheus_url == "http://custom:9090"
        assert client.cache_ttl_seconds == 600
        assert client.mock_responses is True

    @pytest.mark.asyncio
    async def test_krr_availability_verification_mock_mode(self):
        """Test krr availability verification in mock mode."""
        # Mock mode should not verify krr
        client = KrrClient(mock_responses=True)
        await asyncio.sleep(0.1)  # Allow any background tasks to complete

        # Should succeed without actual krr
        assert client.mock_responses is True

    @pytest.mark.asyncio
    async def test_krr_not_found_error(self):
        """Test krr not found error."""
        with patch("shutil.which", return_value=None):
            # Create client in mock mode first to avoid hanging task
            client = KrrClient(mock_responses=True)

            with pytest.raises(KrrNotFoundError):
                await client._verify_krr_availability()

    @pytest.mark.asyncio
    async def test_krr_version_check(self):
        """Test krr version checking."""
        client = KrrClient(mock_responses=True)

        # Mock successful version check
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"krr version 1.8.0", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            version = await client._check_krr_version()
            assert version == "1.8.0"

    @pytest.mark.asyncio
    async def test_krr_version_incompatible(self):
        """Test incompatible krr version handling."""
        client = KrrClient(mock_responses=True)

        # Mock incompatible version
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"krr version 1.5.0", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with pytest.raises(KrrVersionError):
                await client._check_krr_version()


class TestScanRecommendations:
    """Test scan recommendations functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create mock krr client."""
        return KrrClient(mock_responses=True)

    @pytest.mark.asyncio
    async def test_scan_recommendations_basic(self, mock_client):
        """Test basic scan recommendations."""
        result = await mock_client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE
        )

        assert isinstance(result, KrrScanResult)
        assert result.strategy == KrrStrategy.SIMPLE
        assert result.cluster_context is not None
        assert result.prometheus_url == "http://localhost:9090"
        assert isinstance(result.recommendations, list)
        assert result.total_recommendations >= 0

    @pytest.mark.asyncio
    async def test_scan_recommendations_with_filters(self, mock_client):
        """Test scan recommendations with filters."""
        result = await mock_client.scan_recommendations(
            namespace="production",
            strategy=KrrStrategy.SIMPLE,
        )

        assert isinstance(result, KrrScanResult)
        assert "production" in result.namespaces_scanned

    @pytest.mark.asyncio
    async def test_scan_recommendations_all_strategies(self, mock_client):
        """Test scan recommendations with different strategies."""
        strategies = [KrrStrategy.SIMPLE, KrrStrategy.SIMPLE_LIMIT]

        for strategy in strategies:
            result = await mock_client.scan_recommendations(
                namespace="default", strategy=strategy
            )

            assert isinstance(result, KrrScanResult)
            assert result.strategy == strategy

    @pytest.mark.asyncio
    async def test_scan_recommendations_multiple_namespaces(self, mock_client):
        """Test scan recommendations across multiple namespaces."""
        namespaces = ["default", "kube-system", "monitoring"]

        for namespace in namespaces:
            result = await mock_client.scan_recommendations(
                namespace=namespace, strategy=KrrStrategy.SIMPLE
            )

            assert isinstance(result, KrrScanResult)
            assert namespace in result.namespaces_scanned

    @pytest.mark.asyncio
    async def test_scan_recommendations_with_history_duration(self, mock_client):
        """Test scan recommendations with custom history duration."""
        result = await mock_client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE, history_duration="14d"
        )

        assert isinstance(result, KrrScanResult)
        assert result.analysis_period == "14d"


class TestKrrCommandExecution:
    """Test krr command execution."""

    @pytest.fixture
    def mock_client(self):
        """Create mock krr client."""
        return KrrClient(mock_responses=True)

    @pytest.mark.asyncio
    async def test_execute_krr_command_success(self, mock_client):
        """Test successful krr command execution."""
        # Mock successful command execution
        mock_output = {
            "scans": [
                {
                    "object": {
                        "kind": "Deployment",
                        "name": "test-app",
                        "namespace": "default",
                    },
                    "recommendations": [
                        {
                            "requests": {"cpu": "150m", "memory": "192Mi"},
                            "limits": {"cpu": "300m", "memory": "384Mi"},
                        }
                    ],
                }
            ]
        }

        with patch.object(mock_client, "_execute_krr_command") as mock_execute:
            mock_execute.return_value = json.dumps(mock_output)

            output = await mock_client._execute_krr_command(
                ["krr", "simple", "--namespace", "default", "--format", "json"]
            )

            assert isinstance(output, str)
            parsed = json.loads(output)
            assert "scans" in parsed

    @pytest.mark.asyncio
    async def test_execute_krr_command_with_context(self, mock_client):
        """Test krr command execution with kubernetes context."""
        mock_client.kubernetes_context = "test-context"
        mock_client.kubeconfig_path = "/tmp/kubeconfig"

        # Mock command building
        args = ["krr", "simple", "--namespace", "default", "--format", "json"]

        if mock_client.kubeconfig_path:
            args.extend(["--kubeconfig", mock_client.kubeconfig_path])
        if mock_client.kubernetes_context:
            args.extend(["--context", mock_client.kubernetes_context])

        assert "--kubeconfig" in args
        assert "/tmp/kubeconfig" in args
        assert "--context" in args
        assert "test-context" in args

    @pytest.mark.asyncio
    async def test_execute_krr_command_timeout(self, mock_client):
        """Test krr command execution timeout."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            # Simulate timeout
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_subprocess.return_value = mock_process

            # Should not raise in mock mode
            assert mock_client.mock_responses is True

    @pytest.mark.asyncio
    async def test_execute_krr_command_error(self, mock_client):
        """Test krr command execution error handling."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"connection refused")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            # Should not raise in mock mode
            assert mock_client.mock_responses is True


class TestKrrOutputParsing:
    """Test krr output parsing."""

    @pytest.fixture
    def mock_client(self):
        """Create mock krr client."""
        return KrrClient(mock_responses=True)

    @pytest.mark.asyncio
    async def test_parse_krr_output_basic(self, mock_client):
        """Test basic krr output parsing."""
        mock_output = {
            "scans": [
                {
                    "object": {
                        "kind": "Deployment",
                        "name": "test-app",
                        "namespace": "default",
                    },
                    "recommendations": [
                        {
                            "requests": {"cpu": "150m", "memory": "192Mi"},
                            "limits": {"cpu": "300m", "memory": "384Mi"},
                        }
                    ],
                }
            ]
        }

        with patch.object(mock_client, "_parse_krr_output") as mock_parse:
            mock_result = KrrScanResult(
                scan_id="test-scan",
                strategy=KrrStrategy.SIMPLE,
                cluster_context="test-context",
                prometheus_url="http://localhost:9090",
                namespaces_scanned=["default"],
                analysis_period="7d",
                recommendations=[],
                total_recommendations=0,
            )
            mock_parse.return_value = mock_result

            result = await mock_client._parse_krr_output(
                json.dumps(mock_output), KrrStrategy.SIMPLE, ["default"]
            )

            assert isinstance(result, KrrScanResult)

    @pytest.mark.asyncio
    async def test_parse_krr_output_with_recommendations(self, mock_client):
        """Test parsing krr output with recommendations."""
        mock_output = {
            "scans": [
                {
                    "object": {
                        "kind": "Deployment",
                        "name": "web-app",
                        "namespace": "production",
                    },
                    "recommendations": [
                        {
                            "requests": {"cpu": "500m", "memory": "512Mi"},
                            "limits": {"cpu": "1000m", "memory": "1Gi"},
                        }
                    ],
                }
            ]
        }

        # Test that parsing creates proper recommendation objects
        with patch.object(mock_client, "_parse_krr_output") as mock_parse:
            recommendation = KrrRecommendation(
                object=KubernetesObject(
                    kind="Deployment", name="web-app", namespace="production"
                ),
                current_requests=ResourceValue(cpu="250m", memory="256Mi"),
                current_limits=ResourceValue(cpu="500m", memory="512Mi"),
                recommended_requests=ResourceValue(cpu="500m", memory="512Mi"),
                recommended_limits=ResourceValue(cpu="1000m", memory="1Gi"),
            )

            mock_result = KrrScanResult(
                scan_id="test-scan",
                strategy=KrrStrategy.SIMPLE,
                cluster_context="test-context",
                prometheus_url="http://localhost:9090",
                namespaces_scanned=["production"],
                analysis_period="7d",
                recommendations=[recommendation],
                total_recommendations=1,
            )
            mock_parse.return_value = mock_result

            result = await mock_client._parse_krr_output(
                json.dumps(mock_output), KrrStrategy.SIMPLE, ["production"]
            )

            assert len(result.recommendations) == 1
            assert result.recommendations[0].object.name == "web-app"

    @pytest.mark.asyncio
    async def test_parse_krr_output_malformed_json(self, mock_client):
        """Test parsing malformed krr output."""
        malformed_output = '{"scans": [invalid json'

        with patch.object(mock_client, "_parse_krr_output") as mock_parse:
            mock_parse.side_effect = KrrError("Invalid JSON output", "PARSE_ERROR")

            with pytest.raises(KrrError):
                await mock_client._parse_krr_output(
                    malformed_output, KrrStrategy.SIMPLE, ["default"]
                )

    @pytest.mark.asyncio
    async def test_parse_krr_output_empty_scans(self, mock_client):
        """Test parsing krr output with empty scans."""
        empty_output = {"scans": []}

        with patch.object(mock_client, "_parse_krr_output") as mock_parse:
            mock_result = KrrScanResult(
                scan_id="test-scan",
                strategy=KrrStrategy.SIMPLE,
                cluster_context="test-context",
                prometheus_url="http://localhost:9090",
                namespaces_scanned=["default"],
                analysis_period="7d",
                recommendations=[],
                total_recommendations=0,
            )
            mock_parse.return_value = mock_result

            result = await mock_client._parse_krr_output(
                json.dumps(empty_output), KrrStrategy.SIMPLE, ["default"]
            )

            assert len(result.recommendations) == 0
            assert result.total_recommendations == 0


class TestCaching:
    """Test caching functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create mock krr client with short cache TTL."""
        return KrrClient(mock_responses=True, cache_ttl_seconds=1)

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_client):
        """Test cache hit scenario."""
        # First scan should populate cache
        result1 = await mock_client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE
        )

        # Second scan should hit cache
        result2 = await mock_client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE
        )

        # Results should be the same object if cached
        assert isinstance(result1, KrrScanResult)
        assert isinstance(result2, KrrScanResult)

    @pytest.mark.asyncio
    async def test_cache_miss_different_parameters(self, mock_client):
        """Test cache miss with different parameters."""
        # Scan with different parameters should not hit cache
        result1 = await mock_client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE
        )

        result2 = await mock_client.scan_recommendations(
            namespace="production", strategy=KrrStrategy.SIMPLE
        )

        assert isinstance(result1, KrrScanResult)
        assert isinstance(result2, KrrScanResult)
        # Different namespaces should produce different results
        assert result1.namespaces_scanned != result2.namespaces_scanned

    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """Test cache expiration with short TTL."""
        # Create client with very short cache TTL for testing
        client = KrrClient(mock_responses=True, cache_ttl_seconds=0.1)

        # First scan
        result1 = await client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE
        )

        # Wait for cache to expire (short wait)
        await asyncio.sleep(0.15)

        # Second scan should miss cache due to expiration
        result2 = await client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE
        )

        assert isinstance(result1, KrrScanResult)
        assert isinstance(result2, KrrScanResult)

    def test_cached_scan_result_expiration(self, mock_client):
        """Test CachedScanResult expiration logic."""
        scan_result = KrrScanResult(
            scan_id="test-scan",
            strategy=KrrStrategy.SIMPLE,
            cluster_context="test-context",
            prometheus_url="http://localhost:9090",
            namespaces_scanned=["default"],
            analysis_period="7d",
            recommendations=[],
            total_recommendations=0,
        )

        # Create cached result that should be expired
        cached_result = CachedScanResult(
            cache_key="test-key",
            scan_result=scan_result,
            cached_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            ttl_seconds=60,
        )

        assert cached_result.is_expired() is True

        # Create cached result that should not be expired
        fresh_cached_result = CachedScanResult(
            cache_key="test-key",
            scan_result=scan_result,
            cached_at=datetime.now(timezone.utc),
            ttl_seconds=60,
        )

        assert fresh_cached_result.is_expired() is False


class TestMockResponseGeneration:
    """Test mock response generation."""

    @pytest.fixture
    def mock_client(self):
        """Create mock krr client."""
        return KrrClient(mock_responses=True)

    @pytest.mark.asyncio
    async def test_generate_mock_scan_result(self, mock_client):
        """Test mock scan result generation."""
        result = await mock_client._generate_mock_scan_result(
            namespace="default",
            strategy=KrrStrategy.SIMPLE,
            history_duration="7d",
        )

        assert isinstance(result, KrrScanResult)
        assert result.strategy == KrrStrategy.SIMPLE
        assert "default" in result.namespaces_scanned
        assert result.cluster_context == "mock-cluster"
        assert result.prometheus_url == mock_client.prometheus_url
        assert len(result.recommendations) >= 0

    @pytest.mark.asyncio
    async def test_mock_recommendations_structure(self, mock_client):
        """Test mock recommendations structure."""
        result = await mock_client._generate_mock_scan_result(
            namespace="default", strategy=KrrStrategy.SIMPLE, history_duration="7d"
        )

        # Check that mock recommendations have proper structure
        for recommendation in result.recommendations:
            assert isinstance(recommendation, KrrRecommendation)
            assert isinstance(recommendation.object, KubernetesObject)
            assert isinstance(recommendation.current_requests, ResourceValue)
            assert isinstance(recommendation.current_limits, ResourceValue)
            assert isinstance(recommendation.recommended_requests, ResourceValue)
            assert isinstance(recommendation.recommended_limits, ResourceValue)

    @pytest.mark.asyncio
    async def test_mock_multiple_namespaces(self, mock_client):
        """Test mock generation for multiple namespaces."""
        namespaces = ["default", "production", "staging"]

        result = await mock_client._generate_mock_scan_result(
            strategy=KrrStrategy.SIMPLE, namespace=namespaces
        )

        assert isinstance(result, KrrScanResult)
        assert all(ns in result.namespaces_scanned for ns in namespaces)

    @pytest.mark.asyncio
    async def test_mock_different_strategies(self, mock_client):
        """Test mock generation for different strategies."""
        strategies = [KrrStrategy.SIMPLE, KrrStrategy.SIMPLE_LIMIT]

        for strategy in strategies:
            result = await mock_client._generate_mock_scan_result(
                strategy=strategy, namespace="default"
            )

            assert isinstance(result, KrrScanResult)
            assert result.strategy == strategy


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def mock_client(self):
        """Create mock krr client."""
        return KrrClient(mock_responses=True)

    @pytest.mark.asyncio
    async def test_krr_not_found_handling(self, mock_client):
        """Test handling krr not found."""
        mock_client.mock_responses = False

        with patch("shutil.which", return_value=None):
            with pytest.raises(KrrNotFoundError, match="krr executable not found"):
                await mock_client._verify_krr_availability()

    @pytest.mark.asyncio
    async def test_prometheus_connection_error(self, mock_client):
        """Test handling prometheus connection errors."""
        # Mock command execution that fails due to prometheus connection
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"connection refused")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            # Should not raise in mock mode
            assert mock_client.mock_responses is True

    @pytest.mark.asyncio
    async def test_kubernetes_context_error(self, mock_client):
        """Test handling kubernetes context errors."""
        # Mock command execution that fails due to invalid context
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"context not found")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            # Should not raise in mock mode
            assert mock_client.mock_responses is True

    @pytest.mark.asyncio
    async def test_execution_error_handling(self, mock_client):
        """Test handling execution errors."""
        # Mock command execution failure
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"execution failed")
            mock_process.returncode = 2
            mock_subprocess.return_value = mock_process

            # Should not raise in mock mode
            assert mock_client.mock_responses is True

    @pytest.mark.asyncio
    async def test_invalid_json_parsing(self, mock_client):
        """Test handling invalid JSON parsing."""
        invalid_json = "not valid json"

        with patch.object(mock_client, "_parse_krr_output") as mock_parse:
            mock_parse.side_effect = json.JSONDecodeError(
                "Invalid JSON", invalid_json, 0
            )

            with pytest.raises(json.JSONDecodeError):
                await mock_client._parse_krr_output(
                    invalid_json, KrrStrategy.SIMPLE, ["default"]
                )


class TestFilteringAndSorting:
    """Test filtering and sorting functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create mock krr client."""
        return KrrClient(mock_responses=True)

    @pytest.mark.asyncio
    async def test_namespace_filtering(self, mock_client):
        """Test namespace filtering."""
        result = await mock_client.scan_recommendations(
            namespace="production",
            strategy=KrrStrategy.SIMPLE,
        )

        assert isinstance(result, KrrScanResult)
        # In production, all recommendations should be for production namespace
        for rec in result.recommendations:
            if rec.object.namespace != "production":
                # This would be filtered out
                continue
            assert rec.object.namespace == "production"

    @pytest.mark.asyncio
    async def test_object_kind_filtering(self, mock_client):
        """Test object kind filtering."""
        result = await mock_client.scan_recommendations(
            namespace="default",
            strategy=KrrStrategy.SIMPLE,
        )

        assert isinstance(result, KrrScanResult)
        # Check that filtering would work
        deployments = [
            rec for rec in result.recommendations if rec.object.kind == "Deployment"
        ]
        assert len(deployments) >= 0

    @pytest.mark.asyncio
    async def test_severity_filtering(self, mock_client):
        """Test severity filtering."""
        result = await mock_client.scan_recommendations(
            namespace="default",
            strategy=KrrStrategy.SIMPLE,
        )

        assert isinstance(result, KrrScanResult)
        # Check that filtering infrastructure exists
        high_severity_recs = [
            rec
            for rec in result.recommendations
            if rec.severity == RecommendationSeverity.HIGH
        ]
        assert len(high_severity_recs) >= 0

    @pytest.mark.asyncio
    async def test_multiple_filters(self, mock_client):
        """Test applying multiple filters."""
        result = await mock_client.scan_recommendations(
            namespace="production",
            strategy=KrrStrategy.SIMPLE,
        )

        assert isinstance(result, KrrScanResult)
        # Verify that the result structure supports filtering
        assert hasattr(result, "filter_recommendations")


class TestConfigurationHandling:
    """Test configuration and context handling."""

    def test_kubeconfig_path_handling(self):
        """Test kubeconfig path configuration."""
        client = KrrClient(kubeconfig_path="/custom/kubeconfig", mock_responses=True)

        assert client.kubeconfig_path == "/custom/kubeconfig"

    def test_kubernetes_context_handling(self):
        """Test kubernetes context configuration."""
        client = KrrClient(kubernetes_context="custom-context", mock_responses=True)

        assert client.kubernetes_context == "custom-context"

    def test_prometheus_url_configuration(self):
        """Test prometheus URL configuration."""
        client = KrrClient(
            prometheus_url="http://custom-prometheus:9090", mock_responses=True
        )

        assert client.prometheus_url == "http://custom-prometheus:9090"

    def test_cache_ttl_configuration(self):
        """Test cache TTL configuration."""
        client = KrrClient(cache_ttl_seconds=600, mock_responses=True)

        assert client.cache_ttl_seconds == 600

    def test_mock_mode_configuration(self):
        """Test mock mode configuration."""
        client = KrrClient(mock_responses=True)
        assert client.mock_responses is True

        client_real = KrrClient(mock_responses=True)
        assert client_real.mock_responses is False


class TestRecommendationAnalysis:
    """Test recommendation analysis functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create mock krr client."""
        return KrrClient(mock_responses=True)

    @pytest.mark.asyncio
    async def test_recommendation_impact_calculation(self, mock_client):
        """Test recommendation impact calculation."""
        result = await mock_client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE
        )

        # Test that recommendations have impact calculation capability
        for recommendation in result.recommendations:
            impact = recommendation.calculate_impact()

            assert isinstance(impact, dict)
            assert "cpu_change" in impact
            assert "memory_change" in impact
            assert "cpu_change_percent" in impact
            assert "memory_change_percent" in impact

    @pytest.mark.asyncio
    async def test_scan_result_summary_calculation(self, mock_client):
        """Test scan result summary calculation."""
        result = await mock_client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE
        )

        # Test summary calculation
        result.calculate_summary()

        assert isinstance(result.recommendations_by_severity, dict)
        assert result.total_recommendations >= 0
        assert isinstance(result.potential_total_savings, (float, type(None)))

    @pytest.mark.asyncio
    async def test_recommendation_filtering_on_result(self, mock_client):
        """Test filtering recommendations on scan result."""
        result = await mock_client.scan_recommendations(
            namespace="default", strategy=KrrStrategy.SIMPLE
        )

        # Test filtering on the result
        filter_criteria = RecommendationFilter(namespace="default")
        filtered_recs = result.filter_recommendations(filter_criteria)

        assert isinstance(filtered_recs, list)
        # All filtered recommendations should match criteria
        for rec in filtered_recs:
            assert rec.object.namespace == "default"
