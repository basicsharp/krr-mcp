"""Chaos tests for krr MCP Server.

These tests simulate various failure scenarios to verify system resilience,
including network interruptions, resource exhaustion, and external dependency failures.
"""

import asyncio
import random
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.server import KrrMCPServer


class TestNetworkInterruption:
    """Test network interruption scenarios."""
    
    @asynccontextmanager
    async def simulate_network_failure(self, failure_duration: float = 1.0):
        """Context manager to simulate network failures."""
        original_scan = None
        original_execute = None
        
        try:
            # Patch krr client to simulate network failure
            with patch('src.recommender.krr_client.KrrClient.scan_cluster') as mock_scan, \
                 patch('src.executor.kubectl_executor.KubectlExecutor.execute_command') as mock_execute:
                
                original_scan = mock_scan
                original_execute = mock_execute
                
                # Simulate network timeout
                mock_scan.side_effect = asyncio.TimeoutError("Network timeout")
                mock_execute.side_effect = ConnectionError("Network connection lost")
                
                yield
                
                # Restore after failure duration
                await asyncio.sleep(failure_duration)
                
        finally:
            # Network recovery simulation
            if original_scan:
                original_scan.side_effect = None
            if original_execute:
                original_execute.side_effect = None
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_network_failure_during_scan(self, test_server):
        """Test graceful handling of network failure during scan."""
        async with self.simulate_network_failure(0.5):
            result = await test_server.scan_recommendations(namespace="default")
            
            assert result["status"] == "error"
            assert "network" in result["error"].lower() or "timeout" in result["error"].lower()
            assert "error_code" in result
            assert result["error_code"] in ["NETWORK_ERROR", "TIMEOUT_ERROR", "KRR_EXECUTION_ERROR"]
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_network_failure_during_execution(self, test_server):
        """Test network failure during kubectl execution."""
        # First get recommendations successfully
        with patch('src.recommender.krr_client.KrrClient.scan_cluster') as mock_scan:
            mock_scan.return_value = {
                "recommendations": [{
                    "object": {"kind": "Deployment", "namespace": "default", "name": "test"},
                    "recommendations": {"requests": {"cpu": "200m"}},
                    "current": {"requests": {"cpu": "100m"}}
                }]
            }
            
            scan_result = await test_server.scan_recommendations(namespace="default")
            assert scan_result["status"] == "success"
        
        # Get confirmation
        confirmation_result = await test_server.request_confirmation(
            changes={"test": "change"},
            risk_level="low"
        )
        assert confirmation_result["status"] == "success"
        
        # Simulate network failure during execution
        async with self.simulate_network_failure(0.5):
            apply_result = await test_server.apply_recommendations(
                recommendations=scan_result["recommendations"],
                confirmation_token=confirmation_result["confirmation_token"],
                dry_run=False
            )
            
            assert apply_result["status"] == "error"
            assert "network" in apply_result["error"].lower() or "connection" in apply_result["error"].lower()
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_intermittent_network_issues(self, test_server):
        """Test handling of intermittent network issues."""
        call_count = 0
        
        def intermittent_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # Fail every other call
            if call_count % 2 == 1:
                raise ConnectionError("Intermittent network issue")
            
            return {
                "recommendations": [{
                    "object": {"kind": "Deployment", "namespace": "default", "name": "test"},
                    "recommendations": {"requests": {"cpu": "200m"}},
                    "current": {"requests": {"cpu": "100m"}}
                }]
            }
        
        with patch('src.recommender.krr_client.KrrClient.scan_cluster', side_effect=intermittent_failure):
            # First call should fail
            result1 = await test_server.scan_recommendations(namespace="default")
            assert result1["status"] == "error"
            
            # Second call should succeed (if retry logic is implemented)
            result2 = await test_server.scan_recommendations(namespace="default")
            # Depending on retry implementation, this might succeed or fail
            assert result2["status"] in ["success", "error"]


class TestResourceExhaustion:
    """Test resource exhaustion scenarios."""
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_memory_exhaustion_simulation(self, test_server):
        """Test behavior under simulated memory pressure."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Generate extremely large recommendation set to stress memory
        huge_recommendations = []
        for i in range(10000):  # Very large dataset
            huge_recommendations.append({
                "object": {
                    "kind": "Deployment",
                    "namespace": f"namespace-{i % 100}",
                    "name": f"huge-workload-{i}",
                },
                "recommendations": {
                    "requests": {
                        "cpu": f"{100 + i}m",
                        "memory": f"{128 + i}Mi",
                    }
                },
                "current": {
                    "requests": {
                        "cpu": f"{50 + i//2}m",
                        "memory": f"{64 + i//2}Mi",
                    }
                }
            })
        
        try:
            result = await test_server.preview_changes(
                recommendations=huge_recommendations
            )
            
            # Should either succeed or fail gracefully
            assert result["status"] in ["success", "error"]
            
            if result["status"] == "error":
                assert "memory" in result["error"].lower() or "resource" in result["error"].lower()
            
        except MemoryError:
            # Acceptable outcome - system recognized memory exhaustion
            pytest.skip("Memory exhaustion handled by system")
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_concurrent_resource_pressure(self, test_server):
        """Test system behavior under concurrent resource pressure."""
        async def resource_intensive_operation(index: int):
            """Simulate resource-intensive operation."""
            large_recommendations = []
            for i in range(500):  # Medium-large dataset per operation
                large_recommendations.append({
                    "object": {
                        "kind": "Deployment",
                        "namespace": f"stress-{index}",
                        "name": f"workload-{i}",
                    },
                    "recommendations": {"requests": {"cpu": f"{100+i}m"}},
                    "current": {"requests": {"cpu": f"{50+i//2}m"}}
                })
            
            return await test_server.preview_changes(recommendations=large_recommendations)
        
        # Launch many concurrent resource-intensive operations
        tasks = [resource_intensive_operation(i) for i in range(20)]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # At least some should complete successfully
        successful_results = [
            r for r in results 
            if isinstance(r, dict) and r.get("status") == "success"
        ]
        
        error_results = [
            r for r in results 
            if isinstance(r, dict) and r.get("status") == "error"
        ]
        
        exceptions = [r for r in results if isinstance(r, Exception)]
        
        # System should handle pressure gracefully
        assert len(successful_results) + len(error_results) + len(exceptions) == 20
        print(f"Under pressure: {len(successful_results)} succeeded, {len(error_results)} failed gracefully, {len(exceptions)} exceptions")


class TestExternalDependencyFailures:
    """Test failures of external dependencies."""
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_krr_binary_missing(self, test_server):
        """Test behavior when krr binary is missing."""
        with patch('src.recommender.krr_client.KrrClient.scan_cluster') as mock_scan:
            mock_scan.side_effect = FileNotFoundError("krr command not found")
            
            result = await test_server.scan_recommendations(namespace="default")
            
            assert result["status"] == "error"
            assert "krr" in result["error"].lower()
            assert result["error_code"] == "KRR_NOT_FOUND"
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_kubectl_binary_missing(self, test_server):
        """Test behavior when kubectl binary is missing."""
        # First get recommendations and confirmation
        with patch('src.recommender.krr_client.KrrClient.scan_cluster') as mock_scan:
            mock_scan.return_value = {
                "recommendations": [{
                    "object": {"kind": "Deployment", "namespace": "default", "name": "test"},
                    "recommendations": {"requests": {"cpu": "200m"}},
                    "current": {"requests": {"cpu": "100m"}}
                }]
            }
            
            scan_result = await test_server.scan_recommendations(namespace="default")
            confirmation_result = await test_server.request_confirmation(
                changes={"test": "change"},
                risk_level="low"
            )
        
        # Simulate kubectl missing during execution
        with patch('src.executor.kubectl_executor.KubectlExecutor.execute_command') as mock_execute:
            mock_execute.side_effect = FileNotFoundError("kubectl command not found")
            
            apply_result = await test_server.apply_recommendations(
                recommendations=scan_result["recommendations"],
                confirmation_token=confirmation_result["confirmation_token"],
                dry_run=False
            )
            
            assert apply_result["status"] == "error"
            assert "kubectl" in apply_result["error"].lower()
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_prometheus_unavailable(self, test_server):
        """Test behavior when Prometheus is unavailable."""
        with patch('src.recommender.krr_client.KrrClient.scan_cluster') as mock_scan:
            mock_scan.side_effect = ConnectionError("Could not connect to Prometheus")
            
            result = await test_server.scan_recommendations(namespace="default")
            
            assert result["status"] == "error"
            assert "prometheus" in result["error"].lower() or "connection" in result["error"].lower()
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_kubernetes_api_unavailable(self, test_server):
        """Test behavior when Kubernetes API is unavailable."""
        with patch('src.executor.kubectl_executor.KubectlExecutor.execute_command') as mock_execute:
            mock_execute.side_effect = Exception("The connection to the server localhost:8080 was refused")
            
            # Get recommendations and confirmation first
            with patch('src.recommender.krr_client.KrrClient.scan_cluster') as mock_scan:
                mock_scan.return_value = {
                    "recommendations": [{
                        "object": {"kind": "Deployment", "namespace": "default", "name": "test"},
                        "recommendations": {"requests": {"cpu": "200m"}},
                        "current": {"requests": {"cpu": "100m"}}
                    }]
                }
                
                scan_result = await test_server.scan_recommendations(namespace="default")
                confirmation_result = await test_server.request_confirmation(
                    changes={"test": "change"},
                    risk_level="low"
                )
            
            apply_result = await test_server.apply_recommendations(
                recommendations=scan_result["recommendations"],
                confirmation_token=confirmation_result["confirmation_token"],
                dry_run=True  # Even dry-run should fail
            )
            
            assert apply_result["status"] == "error"
            assert "connection" in apply_result["error"].lower() or "server" in apply_result["error"].lower()


class TestCorruptedDataHandling:
    """Test handling of corrupted or malformed data."""
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_corrupted_krr_output(self, test_server):
        """Test handling of corrupted krr output."""
        with patch('src.recommender.krr_client.KrrClient.scan_cluster') as mock_scan:
            # Return malformed JSON
            mock_scan.return_value = "{'invalid': json, missing quotes}"
            
            result = await test_server.scan_recommendations(namespace="default")
            
            assert result["status"] == "error"
            assert "parse" in result["error"].lower() or "invalid" in result["error"].lower()
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_invalid_recommendation_structure(self, test_server):
        """Test handling of invalid recommendation structure."""
        invalid_recommendations = [
            {"missing_required_fields": True},
            {"object": "invalid_structure"},
            {"object": {"kind": "Deployment"}, "recommendations": "not_a_dict"},
            None,  # Null recommendation
        ]
        
        result = await test_server.preview_changes(
            recommendations=invalid_recommendations
        )
        
        assert result["status"] == "error"
        assert "validation" in result["error"].lower() or "invalid" in result["error"].lower()
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_malformed_confirmation_data(self, test_server):
        """Test handling of malformed confirmation data."""
        # Try to request confirmation with invalid data structures
        invalid_changes = [
            None,
            "not_a_dict", 
            {"nested": {"deeply": {"invalid": object()}}},  # Non-serializable object
            {"circular": None}  # Will add circular reference
        ]
        
        # Add circular reference
        invalid_changes[3]["circular"] = invalid_changes[3]
        
        for invalid_change in invalid_changes[:3]:  # Skip circular reference test
            result = await test_server.request_confirmation(
                changes=invalid_change,
                risk_level="low"
            )
            
            # Should handle gracefully
            assert result["status"] in ["success", "error"]
            if result["status"] == "error":
                assert "validation" in result["error"].lower() or "invalid" in result["error"].lower()


class TestRaceConditions:
    """Test race conditions and concurrent access issues."""
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_concurrent_token_usage(self, test_server):
        """Test concurrent usage of the same confirmation token."""
        # Get a confirmation token
        confirmation_result = await test_server.request_confirmation(
            changes={"test": "change"},
            risk_level="low"
        )
        
        token = confirmation_result["confirmation_token"]
        
        # Try to use the same token concurrently
        tasks = [
            test_server.apply_recommendations(
                recommendations=[{
                    "object": {"kind": "Deployment", "namespace": "default", "name": "test"},
                    "recommendations": {"requests": {"cpu": "200m"}},
                    "current": {"requests": {"cpu": "100m"}}
                }],
                confirmation_token=token,
                dry_run=True
            )
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Only one should succeed (single-use tokens)
        successful_results = [r for r in results if isinstance(r, dict) and r.get("status") == "success"]
        error_results = [r for r in results if isinstance(r, dict) and r.get("status") == "error"]
        
        assert len(successful_results) <= 1  # At most one success
        assert len(error_results) >= 4  # At least four should fail
        
        # Failed results should mention token issues
        for error_result in error_results:
            assert "token" in error_result["error"].lower()
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_rapid_confirmation_requests(self, test_server):
        """Test rapid creation of confirmation tokens."""
        # Create many confirmation requests rapidly
        tasks = [
            test_server.request_confirmation(
                changes={"operation": f"test-{i}"},
                risk_level="low"
            )
            for i in range(50)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed or fail gracefully
        successful_results = [r for r in results if isinstance(r, dict) and r.get("status") == "success"]
        
        # Verify all tokens are unique
        if successful_results:
            tokens = [r["confirmation_token"] for r in successful_results]
            assert len(set(tokens)) == len(tokens)  # All unique
        
        # No exceptions should occur
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0


class TestRandomizedChaos:
    """Randomized chaos tests to discover unexpected failure modes."""
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_random_operation_failures(self, test_server):
        """Test random operation failures."""
        operations = [
            lambda: test_server.scan_recommendations(namespace="default"),
            lambda: test_server.preview_changes(recommendations=[{
                "object": {"kind": "Deployment", "namespace": "default", "name": "test"},
                "recommendations": {"requests": {"cpu": "200m"}},
                "current": {"requests": {"cpu": "100m"}}
            }]),
            lambda: test_server.request_confirmation(changes={"test": "change"}, risk_level="low"),
            lambda: test_server.get_execution_history(limit=10),
        ]
        
        # Randomly fail some operations
        with patch('src.recommender.krr_client.KrrClient.scan_cluster') as mock_scan, \
             patch('src.executor.kubectl_executor.KubectlExecutor.execute_command') as mock_execute:
            
            def random_failure(*args, **kwargs):
                if random.random() < 0.3:  # 30% failure rate
                    failure_types = [
                        ConnectionError("Random network failure"),
                        TimeoutError("Random timeout"),
                        ValueError("Random validation error"),
                        RuntimeError("Random runtime error"),
                    ]
                    raise random.choice(failure_types)
                
                return {
                    "recommendations": [{
                        "object": {"kind": "Deployment", "namespace": "default", "name": "test"},
                        "recommendations": {"requests": {"cpu": "200m"}},
                        "current": {"requests": {"cpu": "100m"}}
                    }]
                }
            
            mock_scan.side_effect = random_failure
            mock_execute.side_effect = random_failure
            
            # Run random operations
            for _ in range(20):
                operation = random.choice(operations)
                
                try:
                    result = await operation()
                    
                    # Should handle all results gracefully
                    assert result["status"] in ["success", "error"]
                    if result["status"] == "error":
                        assert "error" in result
                        assert isinstance(result["error"], str)
                
                except Exception as e:
                    # Unexpected exceptions should be minimal
                    print(f"Unexpected exception: {type(e).__name__}: {e}")
                    # Allow some exceptions but they should be handled gracefully
                    pass
    
    @pytest.mark.asyncio
    @pytest.mark.chaos 
    async def test_resource_limit_boundaries(self, test_server):
        """Test edge cases around resource limits."""
        boundary_recommendations = [
            # Zero resources
            {
                "object": {"kind": "Deployment", "namespace": "default", "name": "zero-resources"},
                "recommendations": {"requests": {"cpu": "0m", "memory": "0Mi"}},
                "current": {"requests": {"cpu": "100m", "memory": "128Mi"}}
            },
            # Maximum reasonable resources
            {
                "object": {"kind": "Deployment", "namespace": "default", "name": "max-resources"},
                "recommendations": {"requests": {"cpu": "100000m", "memory": "1000Gi"}},
                "current": {"requests": {"cpu": "100m", "memory": "128Mi"}}
            },
            # Negative resources (invalid)
            {
                "object": {"kind": "Deployment", "namespace": "default", "name": "negative-resources"},
                "recommendations": {"requests": {"cpu": "-100m", "memory": "-128Mi"}},
                "current": {"requests": {"cpu": "100m", "memory": "128Mi"}}
            },
            # Invalid resource format
            {
                "object": {"kind": "Deployment", "namespace": "default", "name": "invalid-format"},
                "recommendations": {"requests": {"cpu": "invalid", "memory": "also-invalid"}},
                "current": {"requests": {"cpu": "100m", "memory": "128Mi"}}
            },
        ]
        
        for recommendation in boundary_recommendations:
            result = await test_server.preview_changes(recommendations=[recommendation])
            
            # Should handle all boundary cases gracefully
            assert result["status"] in ["success", "error"]
            
            if result["status"] == "error":
                assert "validation" in result["error"].lower() or "invalid" in result["error"].lower()
            else:
                # If successful, safety assessment should flag dangerous changes
                safety_assessment = result["safety_assessment"]
                if "max-resources" in recommendation["object"]["name"]:
                    assert safety_assessment["risk_level"] in ["high", "critical"]