"""Tests for krr integration."""

from unittest.mock import AsyncMock, patch

import pytest

from src.recommender.krr_client import KrrClient
from src.recommender.models import KrrStrategy, RecommendationFilter


class TestKrrClient:
    """Test KrrClient class."""

    def test_client_initialization(self):
        """Test client initialization with mock responses."""
        client = KrrClient(
            kubeconfig_path="/test/kubeconfig",
            kubernetes_context="test-context",
            prometheus_url="http://test:9090",
            mock_responses=True,
        )

        assert client.kubeconfig_path == "/test/kubeconfig"
        assert client.kubernetes_context == "test-context"
        assert client.prometheus_url == "http://test:9090"
        assert client.mock_responses is True

    @pytest.mark.asyncio
    async def test_mock_scan_recommendations(self):
        """Test scanning with mock responses."""
        client = KrrClient(mock_responses=True)

        result = await client.scan_recommendations(
            namespace="default",
            strategy=KrrStrategy.SIMPLE,
        )

        assert result.strategy == KrrStrategy.SIMPLE
        assert result.cluster_context == "mock-cluster"
        assert len(result.recommendations) > 0

        # Check first recommendation structure
        first_rec = result.recommendations[0]
        assert first_rec.object.kind == "Deployment"
        assert first_rec.object.name == "test-app"
        assert first_rec.current_requests.cpu == "100m"
        assert first_rec.recommended_requests.cpu == "250m"

    @pytest.mark.asyncio
    async def test_recommendation_filtering(self):
        """Test filtering recommendations."""
        client = KrrClient(mock_responses=True)

        result = await client.scan_recommendations()

        # Test namespace filtering
        filter_criteria = RecommendationFilter(namespace="default")
        filtered = client.filter_recommendations(result, filter_criteria)

        assert len(filtered) > 0
        assert all(rec.object.namespace == "default" for rec in filtered)

    def test_cache_key_generation(self):
        """Test cache key generation."""
        client = KrrClient(
            kubernetes_context="test-context",
            prometheus_url="http://test:9090",
            mock_responses=True,
        )

        key = client._generate_cache_key("default", KrrStrategy.SIMPLE, "7d")

        expected_parts = [
            "cluster:test-context",
            "namespace:default",
            "strategy:simple",
            "history:7d",
            "prometheus:http://test:9090",
        ]
        expected_key = "|".join(expected_parts)

        assert key == expected_key

    def test_cache_management(self):
        """Test cache storage and retrieval."""
        client = KrrClient(mock_responses=True, cache_ttl_seconds=1)

        # Initially no cache
        cache_key = "test-key"
        cached = client._get_cached_result(cache_key)
        assert cached is None

        # Clean up should work even with empty cache
        cleaned = client.cleanup_expired_cache()
        assert cleaned == 0


class TestKrrModels:
    """Test krr data models."""

    def test_krr_recommendation_impact_calculation(self):
        """Test impact calculation."""
        from src.recommender.models import (
            KrrRecommendation,
            KubernetesObject,
            ResourceValue,
        )

        rec = KrrRecommendation(
            object=KubernetesObject(
                kind="Deployment", name="test-app", namespace="default"
            ),
            current_requests=ResourceValue(cpu="100m", memory="128Mi"),
            current_limits=ResourceValue(cpu="200m", memory="256Mi"),
            recommended_requests=ResourceValue(cpu="250m", memory="256Mi"),
            recommended_limits=ResourceValue(cpu="500m", memory="512Mi"),
        )

        impact = rec.calculate_impact()

        # CPU: 100m -> 250m = 150% increase
        assert impact["cpu_change_percent"] == 150.0

        # Memory: 128Mi -> 256Mi = 100% increase
        assert impact["memory_change_percent"] == 100.0

        assert impact["cpu_change"] == 150.0  # millicores
        assert impact["memory_change"] > 0  # bytes

    def test_cpu_parsing(self):
        """Test CPU value parsing."""
        from src.recommender.models import (
            KrrRecommendation,
            KubernetesObject,
            ResourceValue,
        )

        rec = KrrRecommendation(
            object=KubernetesObject(
                kind="Deployment", name="test", namespace="default"
            ),
            current_requests=ResourceValue(),
            current_limits=ResourceValue(),
            recommended_requests=ResourceValue(),
            recommended_limits=ResourceValue(),
        )

        # Test millicores
        assert rec._parse_cpu_value("250m") == 250.0

        # Test cores
        assert rec._parse_cpu_value("1") == 1000.0
        assert rec._parse_cpu_value("0.5") == 500.0

        # Test None
        assert rec._parse_cpu_value(None) is None
        assert rec._parse_cpu_value("") is None

    def test_memory_parsing(self):
        """Test memory value parsing."""
        from src.recommender.models import (
            KrrRecommendation,
            KubernetesObject,
            ResourceValue,
        )

        rec = KrrRecommendation(
            object=KubernetesObject(
                kind="Deployment", name="test", namespace="default"
            ),
            current_requests=ResourceValue(),
            current_limits=ResourceValue(),
            recommended_requests=ResourceValue(),
            recommended_limits=ResourceValue(),
        )

        # Test different units
        assert rec._parse_memory_value("256Mi") == 256 * 1024 * 1024
        assert rec._parse_memory_value("1Gi") == 1024 * 1024 * 1024
        assert rec._parse_memory_value("512Ki") == 512 * 1024

        # Test bytes
        assert rec._parse_memory_value("1024") == 1024.0

        # Test None
        assert rec._parse_memory_value(None) is None
        assert rec._parse_memory_value("") is None
