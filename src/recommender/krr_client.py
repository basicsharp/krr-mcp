"""krr CLI client for Kubernetes resource recommendations.

This module provides a robust wrapper around the krr CLI tool with
async execution, error handling, caching, and safety integration.
"""

import asyncio
import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from .models import (
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
    ResourceValue,
)

logger = structlog.get_logger(__name__)


class KrrClient:
    """Async client for interacting with krr CLI tool."""

    # Minimum supported krr version
    MIN_KRR_VERSION = "1.7.0"

    def __init__(
        self,
        kubeconfig_path: Optional[str] = None,
        kubernetes_context: Optional[str] = None,
        prometheus_url: str = "http://localhost:9090",
        cache_ttl_seconds: int = 300,
        mock_responses: bool = False,
    ):
        """Initialize the krr client.

        Args:
            kubeconfig_path: Path to kubeconfig file
            kubernetes_context: Kubernetes context to use
            prometheus_url: Prometheus server URL
            cache_ttl_seconds: Cache TTL for scan results
            mock_responses: Use mock responses for testing
        """
        self.kubeconfig_path = kubeconfig_path
        self.kubernetes_context = kubernetes_context
        self.prometheus_url = prometheus_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self.mock_responses = mock_responses

        self.logger = structlog.get_logger(self.__class__.__name__)

        # Cache for scan results
        self._cache: Dict[str, CachedScanResult] = {}

        # Verify krr availability on initialization
        if not mock_responses:
            asyncio.create_task(self._verify_krr_availability())

    async def _verify_krr_availability(self) -> None:
        """Verify that krr is available and compatible."""
        try:
            # Check if krr executable exists
            if not shutil.which("krr"):
                raise KrrNotFoundError("krr executable not found in PATH")

            # Check krr version
            await self._check_krr_version()

            self.logger.info("krr client initialized successfully")

        except Exception as e:
            self.logger.error("Failed to verify krr availability", error=str(e))
            raise

    async def _check_krr_version(self) -> str:
        """Check krr version compatibility.

        Returns:
            krr version string

        Raises:
            KrrVersionError: If version is incompatible
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "krr",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise KrrVersionError(
                    f"Failed to get krr version: {stderr.decode()}",
                    current_version=None,
                    required_version=self.MIN_KRR_VERSION,
                )

            version_output = stdout.decode().strip()

            # Extract version number (format: "krr version 1.7.0")
            version_parts = version_output.split()
            if len(version_parts) >= 3:
                current_version = version_parts[2]
            else:
                raise KrrVersionError(
                    f"Cannot parse krr version from: {version_output}",
                    current_version=version_output,
                    required_version=self.MIN_KRR_VERSION,
                )

            # Simple version comparison (assumes semantic versioning)
            if not self._is_version_compatible(current_version, self.MIN_KRR_VERSION):
                raise KrrVersionError(
                    f"krr version {current_version} is not compatible (minimum: {self.MIN_KRR_VERSION})",
                    current_version=current_version,
                    required_version=self.MIN_KRR_VERSION,
                )

            self.logger.info("krr version check passed", version=current_version)
            return current_version

        except asyncio.TimeoutError:
            raise KrrVersionError("Timeout while checking krr version")
        except Exception as e:
            if isinstance(e, KrrVersionError):
                raise
            raise KrrVersionError(f"Error checking krr version: {str(e)}")

    def _is_version_compatible(self, current: str, minimum: str) -> bool:
        """Check if current version meets minimum requirement."""
        try:
            current_parts = [int(x) for x in current.split(".")]
            minimum_parts = [int(x) for x in minimum.split(".")]

            # Pad shorter version with zeros
            max_len = max(len(current_parts), len(minimum_parts))
            current_parts.extend([0] * (max_len - len(current_parts)))
            minimum_parts.extend([0] * (max_len - len(minimum_parts)))

            return current_parts >= minimum_parts

        except ValueError:
            # If version parsing fails, assume compatible
            return True

    async def scan_recommendations(
        self,
        namespace: Optional[str] = None,
        strategy: KrrStrategy = KrrStrategy.SIMPLE,
        history_duration: str = "7d",
        include_limits: bool = True,
        use_cache: bool = True,
    ) -> KrrScanResult:
        """Scan cluster for resource recommendations.

        Args:
            namespace: Kubernetes namespace to analyze (None for all)
            strategy: krr strategy to use
            history_duration: Historical data period to analyze
            include_limits: Whether to include resource limits
            use_cache: Whether to use cached results

        Returns:
            KrrScanResult with recommendations

        Raises:
            KrrError: If scan fails
        """
        self.logger.info(
            "Starting krr scan",
            namespace=namespace,
            strategy=strategy.value,
            history_duration=history_duration,
        )

        # Check cache first
        if use_cache:
            cache_key = self._generate_cache_key(namespace, strategy, history_duration)
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                self.logger.info("Returning cached scan result", cache_key=cache_key)
                return cached_result.scan_result

        # Handle mock responses for testing
        if self.mock_responses:
            return await self._generate_mock_scan_result(
                namespace, strategy, history_duration
            )

        try:
            # Build krr command
            cmd_args = self._build_krr_command(
                namespace=namespace,
                strategy=strategy,
                history_duration=history_duration,
                include_limits=include_limits,
            )

            # Execute krr command
            start_time = datetime.now(timezone.utc)
            raw_output = await self._execute_krr_command(cmd_args)
            scan_duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Parse output
            scan_result = await self._parse_krr_output(
                raw_output=raw_output,
                strategy=strategy,
                history_duration=history_duration,
                scan_duration=scan_duration,
            )

            # Cache result
            if use_cache:
                self._cache_scan_result(cache_key, scan_result)

            self.logger.info(
                "krr scan completed successfully",
                recommendations_count=len(scan_result.recommendations),
                scan_duration=scan_duration,
            )

            return scan_result

        except Exception as e:
            self.logger.error("krr scan failed", error=str(e))
            if isinstance(e, KrrError):
                raise
            raise KrrExecutionError(
                f"Unexpected error during krr scan: {str(e)}", exit_code=-1
            )

    def _build_krr_command(
        self,
        namespace: Optional[str] = None,
        strategy: KrrStrategy = KrrStrategy.SIMPLE,
        history_duration: str = "7d",
        include_limits: bool = True,
    ) -> List[str]:
        """Build krr command arguments.

        Args:
            namespace: Kubernetes namespace to analyze
            strategy: krr strategy to use
            history_duration: Historical data period
            include_limits: Whether to include resource limits

        Returns:
            List of command arguments
        """
        cmd_args = [
            "krr",
            "simple",  # krr subcommand
            "--strategy",
            strategy.value,
            "--history",
            history_duration,
            "--prometheus-url",
            self.prometheus_url,
            "--format",
            "json",  # Ensure JSON output
        ]

        # Add kubeconfig if specified
        if self.kubeconfig_path:
            cmd_args.extend(["--kubeconfig", self.kubeconfig_path])

        # Add context if specified
        if self.kubernetes_context:
            cmd_args.extend(["--context", self.kubernetes_context])

        # Add namespace filter if specified
        if namespace:
            cmd_args.extend(["--namespace", namespace])

        # Add limits inclusion
        if include_limits:
            cmd_args.append("--include-limits")

        return cmd_args

    async def _execute_krr_command(
        self, cmd_args: List[str], timeout: int = 300
    ) -> str:
        """Execute krr command asynchronously.

        Args:
            cmd_args: Command arguments
            timeout: Execution timeout in seconds

        Returns:
            Raw command output

        Raises:
            KrrExecutionError: If command fails
            PrometheusConnectionError: If Prometheus connection fails
            KubernetesContextError: If Kubernetes context is invalid
        """
        try:
            self.logger.debug("Executing krr command", cmd_args=cmd_args)

            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise KrrExecutionError(
                    f"krr command timed out after {timeout} seconds",
                    exit_code=-1,
                )

            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""

            if process.returncode != 0:
                # Analyze error to provide specific error types
                if (
                    "prometheus" in stderr_str.lower()
                    or "connection refused" in stderr_str.lower()
                ):
                    raise PrometheusConnectionError(
                        f"Failed to connect to Prometheus: {stderr_str}",
                        prometheus_url=self.prometheus_url,
                    )

                if (
                    "context" in stderr_str.lower()
                    or "kubeconfig" in stderr_str.lower()
                ):
                    raise KubernetesContextError(
                        f"Kubernetes context error: {stderr_str}",
                        context=self.kubernetes_context,
                    )

                raise KrrExecutionError(
                    f"krr command failed: {stderr_str}",
                    exit_code=process.returncode,
                    stderr=stderr_str,
                )

            if not stdout_str.strip():
                raise KrrExecutionError(
                    "krr command produced no output",
                    exit_code=process.returncode,
                    stderr=stderr_str,
                )

            return stdout_str

        except Exception as e:
            if isinstance(
                e,
                (KrrExecutionError, PrometheusConnectionError, KubernetesContextError),
            ):
                raise
            raise KrrExecutionError(
                f"Unexpected error executing krr: {str(e)}", exit_code=-1
            )

    async def _parse_krr_output(
        self,
        raw_output: str,
        strategy: KrrStrategy,
        history_duration: str,
        scan_duration: float,
    ) -> KrrScanResult:
        """Parse krr JSON output into structured data.

        Args:
            raw_output: Raw JSON output from krr
            strategy: Strategy used for scan
            history_duration: History duration used
            scan_duration: Time taken for scan

        Returns:
            Parsed KrrScanResult

        Raises:
            KrrExecutionError: If parsing fails
        """
        try:
            # Parse JSON output
            krr_data = json.loads(raw_output)

            # Extract recommendations
            recommendations = []
            raw_recommendations = krr_data.get("recommendations", [])

            for raw_rec in raw_recommendations:
                try:
                    recommendation = self._parse_single_recommendation(raw_rec)
                    recommendations.append(recommendation)
                except Exception as e:
                    self.logger.warning(
                        "Failed to parse recommendation",
                        error=str(e),
                        raw_recommendation=raw_rec,
                    )
                    continue

            # Extract metadata
            metadata = krr_data.get("metadata", {})

            # Create scan result
            scan_result = KrrScanResult(
                scan_id=str(uuid.uuid4()),
                strategy=strategy,
                cluster_context=self.kubernetes_context or "default",
                prometheus_url=self.prometheus_url,
                namespaces_scanned=metadata.get("namespaces", ["all"]),
                analysis_period=history_duration,
                recommendations=recommendations,
                total_recommendations=len(recommendations),
                scan_duration_seconds=scan_duration,
                krr_version=metadata.get("krr_version"),
            )

            # Calculate summary statistics
            scan_result.calculate_summary()

            return scan_result

        except json.JSONDecodeError as e:
            raise KrrExecutionError(
                f"Failed to parse krr JSON output: {str(e)}",
                exit_code=-1,
                stderr=f"Invalid JSON: {raw_output[:500]}...",
            )
        except Exception as e:
            raise KrrExecutionError(
                f"Error parsing krr output: {str(e)}",
                exit_code=-1,
                stderr=raw_output[:500],
            )

    def _parse_single_recommendation(
        self, raw_rec: Dict[str, Any]
    ) -> KrrRecommendation:
        """Parse a single recommendation from krr output.

        Args:
            raw_rec: Raw recommendation dict from krr

        Returns:
            Parsed KrrRecommendation
        """
        # Parse object information
        obj_info = raw_rec.get("object", {})
        kubernetes_object = KubernetesObject(
            kind=obj_info.get("kind", "Unknown"),
            name=obj_info.get("name", "Unknown"),
            namespace=obj_info.get("namespace", "default"),
        )

        # Parse current values
        current = raw_rec.get("current", {})
        current_requests = ResourceValue(
            cpu=current.get("requests", {}).get("cpu"),
            memory=current.get("requests", {}).get("memory"),
        )
        current_limits = ResourceValue(
            cpu=current.get("limits", {}).get("cpu"),
            memory=current.get("limits", {}).get("memory"),
        )

        # Parse recommended values
        recommended = raw_rec.get("recommendations", {})
        recommended_requests = ResourceValue(
            cpu=recommended.get("requests", {}).get("cpu"),
            memory=recommended.get("requests", {}).get("memory"),
        )
        recommended_limits = ResourceValue(
            cpu=recommended.get("limits", {}).get("cpu"),
            memory=recommended.get("limits", {}).get("memory"),
        )

        # Create recommendation
        return KrrRecommendation(
            object=kubernetes_object,
            current_requests=current_requests,
            current_limits=current_limits,
            recommended_requests=recommended_requests,
            recommended_limits=recommended_limits,
            potential_savings=raw_rec.get("potential_savings"),
            confidence_score=raw_rec.get("confidence_score"),
            analysis_period=raw_rec.get("analysis_period"),
            cpu_usage_percentile=raw_rec.get("cpu_usage_percentile"),
            memory_usage_percentile=raw_rec.get("memory_usage_percentile"),
        )

    def _generate_cache_key(
        self,
        namespace: Optional[str],
        strategy: KrrStrategy,
        history_duration: str,
    ) -> str:
        """Generate cache key for scan parameters."""
        key_parts = [
            f"cluster:{self.kubernetes_context or 'default'}",
            f"namespace:{namespace or 'all'}",
            f"strategy:{strategy.value}",
            f"history:{history_duration}",
            f"prometheus:{self.prometheus_url}",
        ]
        return "|".join(key_parts)

    def _get_cached_result(self, cache_key: str) -> Optional[CachedScanResult]:
        """Get cached scan result if not expired."""
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired():
                return cached
            else:
                # Remove expired entry
                del self._cache[cache_key]
        return None

    def _cache_scan_result(self, cache_key: str, scan_result: KrrScanResult) -> None:
        """Cache scan result with TTL."""
        cached_result = CachedScanResult(
            cache_key=cache_key,
            scan_result=scan_result,
            ttl_seconds=self.cache_ttl_seconds,
        )
        self._cache[cache_key] = cached_result

        self.logger.debug(
            "Cached scan result", cache_key=cache_key, ttl=self.cache_ttl_seconds
        )

    def cleanup_expired_cache(self) -> int:
        """Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        expired_keys = [
            key for key, cached in self._cache.items() if cached.is_expired()
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            self.logger.info(
                "Cleaned up expired cache entries", count=len(expired_keys)
            )

        return len(expired_keys)

    def filter_recommendations(
        self,
        scan_result: KrrScanResult,
        filter_criteria: RecommendationFilter,
    ) -> List[KrrRecommendation]:
        """Filter recommendations based on criteria.

        Args:
            scan_result: Scan result to filter
            filter_criteria: Filter criteria

        Returns:
            Filtered list of recommendations
        """
        return scan_result.filter_recommendations(filter_criteria)

    async def _generate_mock_scan_result(
        self,
        namespace: Optional[str],
        strategy: KrrStrategy,
        history_duration: str,
    ) -> KrrScanResult:
        """Generate mock scan result for testing."""
        mock_recommendations = [
            KrrRecommendation(
                object=KubernetesObject(
                    kind="Deployment",
                    name="test-app",
                    namespace="default",
                ),
                current_requests=ResourceValue(cpu="100m", memory="128Mi"),
                current_limits=ResourceValue(cpu="200m", memory="256Mi"),
                recommended_requests=ResourceValue(cpu="250m", memory="256Mi"),
                recommended_limits=ResourceValue(cpu="500m", memory="512Mi"),
                potential_savings=15.5,
                confidence_score=0.85,
            ),
            KrrRecommendation(
                object=KubernetesObject(
                    kind="StatefulSet",
                    name="database",
                    namespace="prod",
                ),
                current_requests=ResourceValue(cpu="1000m", memory="2Gi"),
                current_limits=ResourceValue(cpu="2000m", memory="4Gi"),
                recommended_requests=ResourceValue(cpu="750m", memory="1.5Gi"),
                recommended_limits=ResourceValue(cpu="1500m", memory="3Gi"),
                potential_savings=45.0,
                confidence_score=0.92,
            ),
        ]

        # Filter by namespace if specified
        if namespace:
            mock_recommendations = [
                r for r in mock_recommendations if r.object.namespace == namespace
            ]

        scan_result = KrrScanResult(
            scan_id=str(uuid.uuid4()),
            strategy=strategy,
            cluster_context="mock-cluster",
            prometheus_url=self.prometheus_url,
            namespaces_scanned=[namespace] if namespace else ["default", "prod"],
            analysis_period=history_duration,
            recommendations=mock_recommendations,
            total_recommendations=len(mock_recommendations),
            scan_duration_seconds=2.5,
            krr_version="1.7.0-mock",
        )

        scan_result.calculate_summary()
        return scan_result
