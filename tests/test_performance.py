"""Performance tests for KRR MCP Server.

These tests verify performance characteristics under various load conditions,
including large cluster simulations and concurrent request handling.
"""

import asyncio
import time
from typing import List
from unittest.mock import patch

import pytest

from src.server import KrrMCPServer


class TestLargeClusterPerformance:
    """Test performance with large cluster simulations."""
    
    def generate_large_recommendations(self, count: int = 1000) -> List[dict]:
        """Generate large number of mock recommendations."""
        recommendations = []
        
        for i in range(count):
            namespace = f"namespace-{i % 10}"  # 10 different namespaces
            workload_type = ["Deployment", "StatefulSet", "DaemonSet"][i % 3]
            
            recommendations.append({
                "object": {
                    "kind": workload_type,
                    "namespace": namespace,
                    "name": f"workload-{i}",
                },
                "recommendations": {
                    "requests": {
                        "cpu": f"{100 + (i % 500)}m",
                        "memory": f"{128 + (i % 1024)}Mi",
                    },
                    "limits": {
                        "cpu": f"{200 + (i % 1000)}m", 
                        "memory": f"{256 + (i % 2048)}Mi",
                    }
                },
                "current": {
                    "requests": {
                        "cpu": f"{50 + (i % 200)}m",
                        "memory": f"{64 + (i % 512)}Mi",
                    },
                    "limits": {
                        "cpu": f"{100 + (i % 400)}m",
                        "memory": f"{128 + (i % 1024)}Mi",
                    }
                }
            })
        
        return recommendations
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_scan_large_cluster_performance(self, test_server):
        """Test scanning performance with large cluster."""
        large_recommendations = self.generate_large_recommendations(1000)
        
        with patch('src.recommender.krr_client.KrrClient.scan_cluster') as mock_scan:
            mock_scan.return_value = {
                "recommendations": large_recommendations,
                "metadata": {
                    "strategy": "simple",
                    "cluster": "large-test-cluster",
                    "resource_count": 1000,
                }
            }
            
            start_time = time.time()
            
            result = await test_server.scan_recommendations(namespace="all")
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Performance assertions
            assert result["status"] == "success"
            assert len(result["recommendations"]) == 1000
            assert execution_time < 10.0  # Should complete within 10 seconds
            
            print(f"Large cluster scan took {execution_time:.2f}s for 1000 resources")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_preview_large_changes_performance(self, test_server):
        """Test preview performance with many changes."""
        large_recommendations = self.generate_large_recommendations(500)
        
        start_time = time.time()
        
        result = await test_server.preview_changes(
            recommendations=large_recommendations
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        assert result["status"] == "success"
        assert "safety_assessment" in result
        assert execution_time < 5.0  # Should complete within 5 seconds
        
        print(f"Preview of 500 changes took {execution_time:.2f}s")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_memory_usage_large_dataset(self, test_server):
        """Test memory usage with large datasets."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Process large dataset
        large_recommendations = self.generate_large_recommendations(2000)
        
        result = await test_server.preview_changes(
            recommendations=large_recommendations
        )
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        assert result["status"] == "success"
        assert memory_increase < 200  # Should not increase memory by more than 200MB
        
        print(f"Memory increase: {memory_increase:.2f}MB for 2000 resources")


class TestConcurrentRequestPerformance:
    """Test performance under concurrent load."""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_scans_performance(self, test_server):
        """Test concurrent scan performance."""
        async def single_scan(namespace: str):
            return await test_server.scan_recommendations(namespace=namespace)
        
        # Launch 10 concurrent scans
        tasks = [
            single_scan(f"namespace-{i}")
            for i in range(10)
        ]
        
        start_time = time.time()
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify all completed successfully
        successful_results = [r for r in results if isinstance(r, dict) and r.get("status") == "success"]
        
        assert len(successful_results) >= 8  # Allow some failures
        assert execution_time < 15.0  # Should complete within 15 seconds
        
        print(f"10 concurrent scans took {execution_time:.2f}s")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_confirmations_performance(self, test_server):
        """Test concurrent confirmation performance."""
        async def single_confirmation(index: int):
            return await test_server.request_confirmation(
                changes={"resource": f"test-{index}", "action": "update"},
                risk_level="low"
            )
        
        # Launch 20 concurrent confirmations
        tasks = [single_confirmation(i) for i in range(20)]
        
        start_time = time.time()
        
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # All should succeed
        successful_results = [r for r in results if r["status"] == "success"]
        
        assert len(successful_results) == 20
        assert execution_time < 5.0  # Should be fast for confirmations
        
        # Verify all tokens are unique
        tokens = [r["confirmation_token"] for r in successful_results]
        assert len(set(tokens)) == 20
        
        print(f"20 concurrent confirmations took {execution_time:.2f}s")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_mixed_concurrent_operations(self, test_server):
        """Test mixed concurrent operations performance."""
        async def scan_operation():
            return await test_server.scan_recommendations(namespace="default")
        
        async def preview_operation():
            small_recommendations = [{
                "object": {"kind": "Deployment", "namespace": "default", "name": "test"},
                "recommendations": {"requests": {"cpu": "200m"}},
                "current": {"requests": {"cpu": "100m"}}
            }]
            return await test_server.preview_changes(recommendations=small_recommendations)
        
        async def confirmation_operation():
            return await test_server.request_confirmation(
                changes={"test": "change"},
                risk_level="low"
            )
        
        async def history_operation():
            return await test_server.get_execution_history(limit=10)
        
        # Mix of different operations
        tasks = []
        for i in range(5):
            tasks.extend([
                scan_operation(),
                preview_operation(),
                confirmation_operation(),
                history_operation(),
            ])
        
        start_time = time.time()
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Count successful operations
        successful_results = [
            r for r in results 
            if isinstance(r, dict) and r.get("status") == "success"
        ]
        
        assert len(successful_results) >= 15  # Allow some failures
        assert execution_time < 20.0  # Should complete within 20 seconds
        
        print(f"20 mixed concurrent operations took {execution_time:.2f}s")


class TestCachingPerformance:
    """Test caching performance improvements."""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_recommendation_caching_performance(self, test_server):
        """Test that caching improves repeated scan performance."""
        namespace = "performance-test"
        
        # First scan (cold cache)
        start_time = time.time()
        first_result = await test_server.scan_recommendations(namespace=namespace)
        first_time = time.time() - start_time
        
        # Second scan (warm cache) - should be faster
        start_time = time.time()
        second_result = await test_server.scan_recommendations(namespace=namespace)
        second_time = time.time() - start_time
        
        assert first_result["status"] == "success"
        assert second_result["status"] == "success"
        
        # Second call should be significantly faster due to caching
        # Allow some tolerance for test environment variations
        if first_time > 0.1:  # Only test if first call took measurable time
            assert second_time < first_time * 0.8  # At least 20% faster
        
        print(f"First scan: {first_time:.3f}s, Second scan: {second_time:.3f}s")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_safety_assessment_caching(self, test_server):
        """Test safety assessment caching performance."""
        recommendations = [{
            "object": {"kind": "Deployment", "namespace": "default", "name": "test"},
            "recommendations": {"requests": {"cpu": "200m", "memory": "256Mi"}},
            "current": {"requests": {"cpu": "100m", "memory": "128Mi"}}
        }]
        
        # First preview (cold cache)
        start_time = time.time()
        first_result = await test_server.preview_changes(recommendations=recommendations)
        first_time = time.time() - start_time
        
        # Second preview (warm cache)
        start_time = time.time()
        second_result = await test_server.preview_changes(recommendations=recommendations)
        second_time = time.time() - start_time
        
        assert first_result["status"] == "success"
        assert second_result["status"] == "success"
        
        # Should have similar results
        assert (first_result["safety_assessment"]["risk_level"] == 
                second_result["safety_assessment"]["risk_level"])
        
        print(f"First preview: {first_time:.3f}s, Second preview: {second_time:.3f}s")


class TestResourceUtilizationBenchmarks:
    """Benchmark resource utilization patterns."""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_cpu_intensive_operations(self, test_server):
        """Test CPU-intensive operations performance."""
        # Generate complex safety assessments
        complex_recommendations = []
        
        for i in range(100):
            complex_recommendations.append({
                "object": {
                    "kind": "Deployment",
                    "namespace": "production" if i % 5 == 0 else "default",
                    "name": f"critical-app-{i}" if i % 10 == 0 else f"app-{i}",
                },
                "recommendations": {
                    "requests": {
                        "cpu": f"{1000 + (i * 100)}m",
                        "memory": f"{2048 + (i * 256)}Mi",
                    }
                },
                "current": {
                    "requests": {
                        "cpu": f"{100 + (i * 10)}m",
                        "memory": f"{256 + (i * 32)}Mi",
                    }
                }
            })
        
        start_time = time.time()
        
        result = await test_server.preview_changes(
            recommendations=complex_recommendations
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        assert result["status"] == "success"
        assert execution_time < 8.0  # Should complete within 8 seconds
        
        print(f"Complex safety assessment took {execution_time:.2f}s for 100 resources")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_memory_efficient_processing(self, test_server):
        """Test memory-efficient processing of large datasets."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # Process recommendations in batches to test memory efficiency
        batch_size = 250
        total_processed = 0
        max_memory_usage = 0
        
        for batch in range(4):  # 4 batches of 250 = 1000 total
            recommendations = self.generate_large_recommendations(batch_size)
            
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            result = await test_server.preview_changes(
                recommendations=recommendations
            )
            
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            max_memory_usage = max(max_memory_usage, current_memory - initial_memory)
            
            assert result["status"] == "success"
            total_processed += len(recommendations)
        
        assert total_processed == 1000
        assert max_memory_usage < 150  # Should not use more than 150MB per batch
        
        print(f"Processed 1000 resources in batches, max memory per batch: {max_memory_usage:.2f}MB")
    
    def generate_large_recommendations(self, count: int) -> List[dict]:
        """Helper method to generate recommendations for performance tests."""
        recommendations = []
        
        for i in range(count):
            namespace = f"namespace-{i % 10}"
            workload_type = ["Deployment", "StatefulSet", "DaemonSet"][i % 3]
            
            recommendations.append({
                "object": {
                    "kind": workload_type,
                    "namespace": namespace,
                    "name": f"workload-{i}",
                },
                "recommendations": {
                    "requests": {
                        "cpu": f"{100 + (i % 500)}m",
                        "memory": f"{128 + (i % 1024)}Mi",
                    }
                },
                "current": {
                    "requests": {
                        "cpu": f"{50 + (i % 200)}m",
                        "memory": f"{64 + (i % 512)}Mi",
                    }
                }
            })
        
        return recommendations


class TestPerformanceRegression:
    """Test for performance regressions."""
    
    performance_baselines = {
        "small_scan": 2.0,      # seconds
        "medium_preview": 3.0,   # seconds  
        "large_preview": 5.0,    # seconds
        "concurrent_ops": 10.0,  # seconds
    }
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_small_operation_baseline(self, test_server):
        """Test baseline performance for small operations."""
        start_time = time.time()
        
        result = await test_server.scan_recommendations(namespace="default")
        
        execution_time = time.time() - start_time
        
        assert result["status"] == "success"
        assert execution_time < self.performance_baselines["small_scan"]
        
        print(f"Small scan baseline: {execution_time:.3f}s (limit: {self.performance_baselines['small_scan']}s)")
    
    @pytest.mark.asyncio 
    @pytest.mark.performance
    async def test_medium_operation_baseline(self, test_server):
        """Test baseline performance for medium operations."""
        recommendations = self.generate_medium_recommendations()
        
        start_time = time.time()
        
        result = await test_server.preview_changes(recommendations=recommendations)
        
        execution_time = time.time() - start_time
        
        assert result["status"] == "success"
        assert execution_time < self.performance_baselines["medium_preview"]
        
        print(f"Medium preview baseline: {execution_time:.3f}s (limit: {self.performance_baselines['medium_preview']}s)")
    
    def generate_medium_recommendations(self) -> List[dict]:
        """Generate medium-sized recommendation set."""
        return [{
            "object": {
                "kind": "Deployment",
                "namespace": f"namespace-{i}",
                "name": f"app-{i}",
            },
            "recommendations": {
                "requests": {
                    "cpu": f"{100 + i * 10}m",
                    "memory": f"{128 + i * 16}Mi",
                }
            },
            "current": {
                "requests": {
                    "cpu": f"{50 + i * 5}m",
                    "memory": f"{64 + i * 8}Mi",
                }
            }
        } for i in range(50)]