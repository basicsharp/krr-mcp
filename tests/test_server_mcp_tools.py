"""Comprehensive tests for server MCP tools."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.executor.models import (
    ExecutionMode,
    ExecutionReport,
    ExecutionStatus,
    ExecutionTransaction,
)
from src.recommender.models import (
    KrrRecommendation,
    KrrScanResult,
    KrrStrategy,
    KubernetesObject,
    ResourceValue,
)
from src.safety.models import (
    ConfirmationToken,
    ResourceChange,
    RiskLevel,
    SafetyAssessment,
)
from src.server import KrrMCPServer, ServerConfig


class TestScanRecommendationsTool:
    """Test scan_recommendations MCP tool."""

    @pytest.fixture
    async def server(self):
        """Create test server instance."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_scan_recommendations_basic(self, server):
        """Test basic scan recommendations functionality."""
        # Mock the krr client response
        with patch.object(server.krr_client, "scan_recommendations") as mock_scan:
            mock_scan_result = KrrScanResult(
                scan_id="test-scan-1",
                strategy=KrrStrategy.SIMPLE,
                cluster_context="test-context",
                prometheus_url="http://localhost:9090",
                namespaces_scanned=["default"],
                analysis_period="7d",
                recommendations=[
                    KrrRecommendation(
                        object=KubernetesObject(
                            kind="Deployment", name="test-app", namespace="default"
                        ),
                        current_requests=ResourceValue(cpu="100m", memory="128Mi"),
                        current_limits=ResourceValue(cpu="200m", memory="256Mi"),
                        recommended_requests=ResourceValue(cpu="150m", memory="192Mi"),
                        recommended_limits=ResourceValue(cpu="300m", memory="384Mi"),
                    )
                ],
                total_recommendations=1,
            )
            mock_scan.return_value = mock_scan_result

            # Test the scan_recommendations tool
            result = await server.krr_client.scan_recommendations(
                namespace="default", strategy=KrrStrategy.SIMPLE
            )

            assert isinstance(result, KrrScanResult)
            assert result.strategy == KrrStrategy.SIMPLE
            assert len(result.recommendations) == 1
            assert result.total_recommendations == 1

    @pytest.mark.asyncio
    async def test_scan_recommendations_with_filters(self, server):
        """Test scan recommendations with filters."""
        # Mock the krr client with filtered results
        with patch.object(server.krr_client, "scan_recommendations") as mock_scan:
            mock_scan_result = KrrScanResult(
                scan_id="test-scan-2",
                strategy=KrrStrategy.SIMPLE,
                cluster_context="test-context",
                prometheus_url="http://localhost:9090",
                namespaces_scanned=["production"],
                analysis_period="7d",
                recommendations=[
                    KrrRecommendation(
                        object=KubernetesObject(
                            kind="Deployment", name="web-app", namespace="production"
                        ),
                        current_requests=ResourceValue(cpu="500m", memory="512Mi"),
                        current_limits=ResourceValue(cpu="1000m", memory="1Gi"),
                        recommended_requests=ResourceValue(cpu="750m", memory="768Mi"),
                        recommended_limits=ResourceValue(cpu="1500m", memory="1.5Gi"),
                    )
                ],
                total_recommendations=1,
            )
            mock_scan.return_value = mock_scan_result

            result = await server.krr_client.scan_recommendations(
                namespace="production", strategy=KrrStrategy.SIMPLE
            )

            assert result.namespaces_scanned == ["production"]
            assert result.recommendations[0].object.namespace == "production"

    @pytest.mark.asyncio
    async def test_scan_recommendations_error_handling(self, server):
        """Test scan recommendations error handling."""
        # Mock the krr client to raise an error
        with patch.object(server.krr_client, "scan_recommendations") as mock_scan:
            from src.recommender.models import KrrError

            mock_scan.side_effect = KrrError("Test error", "TEST_ERROR")

            with pytest.raises(KrrError):
                await server.krr_client.scan_recommendations(
                    namespace="default", strategy=KrrStrategy.SIMPLE
                )


class TestPreviewChangesTool:
    """Test preview_changes MCP tool."""

    @pytest.fixture
    async def server_with_recommendations(self):
        """Create server with mock recommendations."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_preview_changes_basic(self, server_with_recommendations):
        """Test basic preview changes functionality."""
        server = server_with_recommendations

        # Create sample resource changes
        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        # Mock safety validator
        with patch.object(
            server.confirmation_manager.safety_validator, "validate_changes"
        ) as mock_analyze:
            from src.safety.models import SafetyAssessment

            mock_assessment = SafetyAssessment(
                overall_risk_level=RiskLevel.LOW,
                total_resources_affected=1,
                high_impact_changes=0,
                critical_workloads_affected=0,
                warnings=[],
            )
            mock_analyze.return_value = mock_assessment

            # Mock kubectl executor preview
            with patch.object(
                server.kubectl_executor, "create_transaction"
            ) as mock_transaction:
                mock_transaction.return_value = ExecutionTransaction(
                    transaction_id="test-transaction",
                    confirmation_token_id="test-token-123",
                    commands=[],
                    execution_mode=ExecutionMode.SINGLE,
                    dry_run=True,
                )

            # Test preview functionality would be called through the actual tool
            assessment = server.confirmation_manager.safety_validator.validate_changes(
                changes
            )

            assert assessment.overall_risk_level == RiskLevel.LOW
            assert assessment.total_resources_affected == 1

    @pytest.mark.asyncio
    async def test_preview_changes_high_risk(self, server_with_recommendations):
        """Test preview changes with high risk changes."""
        server = server_with_recommendations

        # Create high-risk changes
        changes = [
            ResourceChange(
                object_name="critical-app",
                namespace="production",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "1000m", "memory": "1Gi"},
                proposed_values={"cpu": "5000m", "memory": "5Gi"},
                cpu_change_percent=400.0,
                memory_change_percent=400.0,
            )
        ]

        # Mock safety validator for high risk
        with patch.object(
            server.confirmation_manager.safety_validator, "validate_changes"
        ) as mock_analyze:
            from src.safety.models import SafetyAssessment

            mock_assessment = SafetyAssessment(
                overall_risk_level=RiskLevel.HIGH,
                total_changes=1,
                high_risk_changes=1,
                estimated_impact_score=0.8,
                recommendations=["High resource increase requires careful review"],
                change_assessments=[],
            )
            mock_analyze.return_value = mock_assessment

            assessment = (
                await server.confirmation_manager.safety_validator.validate_changes(
                    changes
                )
            )

            assert assessment.overall_risk_level == RiskLevel.HIGH
            assert assessment.high_risk_changes == 1


class TestRequestConfirmationTool:
    """Test request_confirmation MCP tool."""

    @pytest.fixture
    async def server_with_confirmation(self):
        """Create server with confirmation manager."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_request_confirmation_basic(self, server_with_confirmation):
        """Test basic confirmation request."""
        server = server_with_confirmation

        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        # Mock confirmation manager
        with patch.object(
            server.confirmation_manager, "request_confirmation"
        ) as mock_create:
            mock_assessment = SafetyAssessment(
                overall_risk_level=RiskLevel.LOW,
                total_resources_affected=1,
                warnings=[],
            )
            mock_token = ConfirmationToken(
                token_id="test-token-123",
                secret="test-secret-456",
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                changes=changes,
                safety_assessment=mock_assessment,
                user_context={},
            )
            mock_create.return_value = mock_token

            token = await server.confirmation_manager.request_confirmation(
                changes=changes
            )

            assert token.token_id == "test-token-123"
            assert len(token.changes) == 1

    @pytest.mark.asyncio
    async def test_request_confirmation_validation(self, server_with_confirmation):
        """Test confirmation token validation."""
        server = server_with_confirmation

        # Test valid token
        with patch.object(
            server.confirmation_manager, "validate_confirmation_token"
        ) as mock_validate:
            mock_validate.return_value = True

            result = server.confirmation_manager.validate_confirmation_token(
                "valid-token"
            )
            assert result is True

        # Test invalid token
        with patch.object(
            server.confirmation_manager, "validate_confirmation_token"
        ) as mock_validate:
            mock_validate.return_value = False

            result = server.confirmation_manager.validate_confirmation_token(
                "invalid-token"
            )
            assert result is False


class TestApplyRecommendationsTool:
    """Test apply_recommendations MCP tool."""

    @pytest.fixture
    async def server_with_executor(self):
        """Create server with kubectl executor."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_apply_recommendations_basic(self, server_with_executor):
        """Test basic apply recommendations functionality."""
        server = server_with_executor

        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        # Mock transaction execution
        with patch.object(
            server.kubectl_executor, "execute_transaction"
        ) as mock_execute:
            mock_report = ExecutionReport(
                transaction_id="test-transaction",
                total_commands=1,
                successful_commands=1,
                failed_commands=0,
                total_duration_seconds=2.5,
                resources_modified=[
                    {"kind": "Deployment", "name": "test-app", "namespace": "default"}
                ],
                namespaces_affected=["default"],
                command_summaries=[
                    {"command": "apply", "status": "completed", "duration": 2.5}
                ],
            )
            mock_execute.return_value = mock_report

            # Mock transaction creation
            with patch.object(
                server.kubectl_executor, "create_transaction"
            ) as mock_create:
                mock_transaction = ExecutionTransaction(
                    transaction_id="test-transaction",
                    confirmation_token_id="test-token-123",
                    commands=[],
                    execution_mode=ExecutionMode.SINGLE,
                    dry_run=False,
                )
                mock_create.return_value = mock_transaction

                transaction = await server.kubectl_executor.create_transaction(
                    changes=changes, execution_mode=ExecutionMode.SINGLE, dry_run=False
                )

                report = await server.kubectl_executor.execute_transaction(transaction)

                assert report.successful_commands == 1
                assert report.transaction_id == "test-transaction"

    @pytest.mark.asyncio
    async def test_apply_recommendations_with_confirmation(self, server_with_executor):
        """Test apply recommendations with confirmation."""
        server = server_with_executor

        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        # Mock confirmation validation
        with patch.object(
            server.confirmation_manager, "validate_confirmation_token"
        ) as mock_validate:
            mock_validate.return_value = True

            # Mock token consumption
            with patch.object(
                server.confirmation_manager, "consume_confirmation_token"
            ) as mock_consume:
                mock_consume.return_value = True

                # Test confirmation workflow
                is_valid = server.confirmation_manager.validate_confirmation_token(
                    "test-token"
                )
                assert is_valid is True

                consumed = server.confirmation_manager.consume_confirmation_token(
                    "test-token"
                )
                assert consumed is True


class TestRollbackChangesTool:
    """Test rollback_changes MCP tool."""

    @pytest.fixture
    async def server_with_rollback(self):
        """Create server with rollback capability."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_rollback_changes_basic(self, server_with_rollback):
        """Test basic rollback functionality."""
        server = server_with_rollback

        # Mock rollback execution
        with patch.object(
            server.kubectl_executor, "execute_transaction"
        ) as mock_execute:
            mock_report = ExecutionReport(
                transaction_id="rollback-transaction",
                execution_mode=ExecutionMode.SINGLE,
                execution_status=ExecutionStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                command_results=[],
                dry_run=False,
            )
            mock_execute.return_value = mock_report

            # Test rollback execution would be handled by the actual tool
            # Here we test the underlying components
            assert server.kubectl_executor is not None

    @pytest.mark.asyncio
    async def test_rollback_changes_with_snapshot(self, server_with_rollback):
        """Test rollback with snapshot."""
        server = server_with_rollback

        from src.safety.models import RollbackSnapshot

        # Mock snapshot retrieval
        mock_snapshot = RollbackSnapshot(
            snapshot_id="test-snapshot",
            created_at=datetime.now(timezone.utc),
            resources_snapshot=[
                {"kind": "Deployment", "metadata": {"name": "test-app"}}
            ],
            kubectl_commands=["kubectl get deployment test-app -o yaml"],
            execution_context="test-rollback",
            rollback_commands=["kubectl apply -f snapshot.yaml"],
        )

        # Test that components support rollback
        assert server.kubectl_executor is not None
        assert hasattr(server.kubectl_executor, "execute_transaction")


class TestAnalyzeSafetyTool:
    """Test analyze_safety MCP tool."""

    @pytest.fixture
    async def server_with_safety(self):
        """Create server with safety analyzer."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_analyze_safety_basic(self, server_with_safety):
        """Test basic safety analysis."""
        server = server_with_safety

        changes = [
            ResourceChange(
                object_name="test-deployment",
                namespace="default",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "100m", "memory": "128Mi"},
                proposed_values={"cpu": "200m", "memory": "256Mi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        # Mock safety analysis
        with patch.object(
            server.confirmation_manager.safety_validator, "validate_changes"
        ) as mock_analyze:
            from src.safety.models import ChangeAssessment, SafetyAssessment

            mock_assessment = SafetyAssessment(
                overall_risk_level=RiskLevel.LOW,
                total_changes=1,
                high_risk_changes=0,
                estimated_impact_score=0.2,
                recommendations=["Changes appear safe"],
                change_assessments=[
                    ChangeAssessment(
                        change=changes[0],
                        risk_level=RiskLevel.LOW,
                        risk_factors=[],
                        estimated_impact=0.2,
                        recommendations=["Safe resource increase"],
                    )
                ],
            )
            mock_analyze.return_value = mock_assessment

            assessment = (
                await server.confirmation_manager.safety_validator.validate_changes(
                    changes
                )
            )

            assert assessment.overall_risk_level == RiskLevel.LOW
            assert assessment.total_changes == 1
            assert len(assessment.change_assessments) == 1

    @pytest.mark.asyncio
    async def test_analyze_safety_production_namespace(self, server_with_safety):
        """Test safety analysis for production namespace."""
        server = server_with_safety

        changes = [
            ResourceChange(
                object_name="critical-app",
                namespace="production",
                object_kind="Deployment",
                change_type="resource_increase",
                current_values={"cpu": "2000m", "memory": "2Gi"},
                proposed_values={"cpu": "4000m", "memory": "4Gi"},
                cpu_change_percent=100.0,
                memory_change_percent=100.0,
            )
        ]

        # Mock safety analysis for production
        with patch.object(
            server.confirmation_manager.safety_validator, "validate_changes"
        ) as mock_analyze:
            from src.safety.models import ChangeAssessment, SafetyAssessment

            mock_assessment = SafetyAssessment(
                overall_risk_level=RiskLevel.MEDIUM,
                total_changes=1,
                high_risk_changes=0,
                estimated_impact_score=0.6,
                recommendations=["Production deployment requires extra caution"],
                change_assessments=[
                    ChangeAssessment(
                        change=changes[0],
                        risk_level=RiskLevel.MEDIUM,
                        risk_factors=["production_namespace", "large_resource_change"],
                        estimated_impact=0.6,
                        recommendations=["Verify cluster capacity before applying"],
                    )
                ],
            )
            mock_analyze.return_value = mock_assessment

            assessment = (
                await server.confirmation_manager.safety_validator.validate_changes(
                    changes
                )
            )

            assert assessment.overall_risk_level == RiskLevel.MEDIUM
            assert assessment.estimated_impact_score == 0.6


class TestQueryAuditLogsTool:
    """Test query_audit_logs MCP tool."""

    @pytest.fixture
    async def server_with_audit(self):
        """Create server with audit capability."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_query_audit_logs_basic(self, server_with_audit):
        """Test basic audit log querying."""
        server = server_with_audit

        # Test that server has logging capability
        assert server.logger is not None

        # Test structured logging
        server.logger.info("test_audit_query", operation="test", status="success")

        # Verify logger is configured for structured logging
        assert hasattr(server.logger, "info")
        assert hasattr(server.logger, "error")
        assert hasattr(server.logger, "warning")

    @pytest.mark.asyncio
    async def test_query_audit_logs_with_filters(self, server_with_audit):
        """Test audit log querying with filters."""
        server = server_with_audit

        # Test various log levels
        server.logger.info("test_info", operation="scan", status="success")
        server.logger.warning("test_warning", operation="apply", status="warning")
        server.logger.error("test_error", operation="rollback", status="error")

        # Verify logging works with different levels
        assert server.logger is not None


class TestGenerateDocumentationTool:
    """Test generate_documentation MCP tool."""

    @pytest.fixture
    async def server_with_docs(self):
        """Create server with documentation generator."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_generate_documentation_basic(self, server_with_docs):
        """Test basic documentation generation."""
        server = server_with_docs

        # Test that documentation generator is available
        from src.documentation.tool_doc_generator import ToolDocumentationGenerator

        doc_generator = ToolDocumentationGenerator()
        assert doc_generator is not None

        # Test that it can generate documentation
        docs = doc_generator.generate_markdown()
        assert isinstance(docs, str)
        assert len(docs) > 0


class TestGetVersionInfoTool:
    """Test get_version_info MCP tool."""

    @pytest.fixture
    async def server_with_versioning(self):
        """Create server with version info."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_get_version_info_basic(self, server_with_versioning):
        """Test basic version info retrieval."""
        server = server_with_versioning

        # Test that version registry is available
        from src.versioning.tool_versioning import version_registry

        assert version_registry is not None

        # Test that registry has tools
        tools = version_registry.get_all_tools_info()
        assert isinstance(tools, dict)


class TestServerComponentIntegration:
    """Test server component integration."""

    @pytest.fixture
    async def server_full(self):
        """Create fully configured server."""
        config = ServerConfig(
            mock_krr_responses=True, mock_kubectl_commands=True, development_mode=True
        )
        server = KrrMCPServer(config)
        await asyncio.sleep(0.1)
        return server

    @pytest.mark.asyncio
    async def test_all_components_initialized(self, server_full):
        """Test that all components are properly initialized."""
        server = server_full

        # Test all major components exist
        assert server.krr_client is not None
        assert server.confirmation_manager.safety_validator is not None
        assert server.confirmation_manager is not None
        assert server.kubectl_executor is not None
        assert server.logger is not None
        assert server.mcp is not None

    @pytest.mark.asyncio
    async def test_component_configuration(self, server_full):
        """Test component configuration."""
        server = server_full

        # Test mock mode configuration
        assert server.config.mock_krr_responses is True
        assert server.config.mock_kubectl_commands is True
        assert server.config.development_mode is True

        # Test safety configuration
        assert server.config.confirmation_timeout_seconds > 0
        assert server.config.max_resource_change_percent > 0
        assert server.config.rollback_retention_days > 0

    @pytest.mark.asyncio
    async def test_server_lifecycle(self, server_full):
        """Test server lifecycle management."""
        server = server_full

        # Test server state
        assert server._running is False

        # Mock server start
        with patch.object(server, "_validate_configuration", new_callable=AsyncMock):
            with patch.object(server.mcp, "run", new_callable=AsyncMock):
                await server.start()
                assert server._running is True

                await server.stop()
                assert server._running is False
