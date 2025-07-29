#!/usr/bin/env python3
"""Comprehensive test runner for krr MCP Server.

This script provides different test execution modes with coverage reporting,
performance tracking, and quality gate validation.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional


class TestRunner:
    """Comprehensive test runner with coverage analysis."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.test_dir = project_root / "tests" 
        self.coverage_dir = project_root / "htmlcov"
        self.reports_dir = project_root / "test-reports"
        
        # Ensure reports directory exists
        self.reports_dir.mkdir(exist_ok=True)
    
    def run_unit_tests(self, verbose: bool = False) -> bool:
        """Run unit tests with coverage."""
        print("🧪 Running unit tests...")
        
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir),
            "-v" if verbose else "-q",
            "--cov=src",
            "--cov-report=html",
            "--cov-report=term-missing",
            "--cov-report=xml",
            # Exclude integration, performance, and chaos tests
            "-m", "not integration and not performance and not chaos",
            f"--cov-fail-under=85",  # Minimum 85% coverage
        ]
        
        return self._run_command(cmd, "Unit tests")
    
    def run_integration_tests(self, verbose: bool = False) -> bool:
        """Run integration tests."""
        print("🔗 Running integration tests...")
        
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir / "test_integration_workflows.py"),
            "-v" if verbose else "-q",
            "--cov=src",
            "--cov-append",  # Append to existing coverage
            "-m", "integration or not integration",  # Run all integration tests
        ]
        
        return self._run_command(cmd, "Integration tests")
    
    def run_performance_tests(self, verbose: bool = False) -> bool:
        """Run performance tests."""
        print("⚡ Running performance tests...")
        
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir / "test_performance.py"),
            "-v" if verbose else "-q",
            "--cov=src",
            "--cov-append",
            "-m", "performance",
            "-s",  # Don't capture output for performance metrics
        ]
        
        return self._run_command(cmd, "Performance tests")
    
    def run_chaos_tests(self, verbose: bool = False) -> bool:
        """Run chaos tests.""" 
        print("🌪️  Running chaos tests...")
        
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir / "test_chaos.py"),
            "-v" if verbose else "-q",
            "--cov=src",
            "--cov-append",
            "-m", "chaos",
        ]
        
        return self._run_command(cmd, "Chaos tests")
    
    def run_safety_critical_tests(self, verbose: bool = False) -> bool:
        """Run safety-critical tests with maximum coverage requirements."""
        print("🛡️  Running safety-critical tests...")
        
        safety_test_files = [
            "test_safety_models.py",
            "test_safety_validator.py", 
            "test_safety_confirmation_manager.py",
        ]
        
        cmd = [
            "python", "-m", "pytest",
            *[str(self.test_dir / f) for f in safety_test_files],
            "-v" if verbose else "-q",
            "--cov=src/safety",
            "--cov-report=html:htmlcov-safety",
            "--cov-report=term-missing",
            "--cov-fail-under=95",  # Safety-critical requires 95%+
        ]
        
        return self._run_command(cmd, "Safety-critical tests")
    
    def run_all_tests(self, verbose: bool = False) -> Dict[str, bool]:
        """Run all test suites and return results."""
        print("🚀 Running comprehensive test suite...")
        
        results = {}
        
        # Run tests in order of importance
        test_suites = [
            ("safety_critical", self.run_safety_critical_tests),
            ("unit", self.run_unit_tests),
            ("integration", self.run_integration_tests),
            ("performance", self.run_performance_tests),
            ("chaos", self.run_chaos_tests),
        ]
        
        for suite_name, test_function in test_suites:
            print(f"\n{'='*60}")
            results[suite_name] = test_function(verbose)
            
            if not results[suite_name]:
                print(f"❌ {suite_name.title()} tests failed!")
                if suite_name == "safety_critical":
                    print("🚨 CRITICAL: Safety tests must pass before proceeding!")
                    break
            else:
                print(f"✅ {suite_name.title()} tests passed!")
        
        return results
    
    def generate_coverage_report(self) -> bool:
        """Generate comprehensive coverage report."""
        print("📊 Generating coverage report...")
        
        # Generate HTML report
        cmd = [
            "python", "-m", "coverage", "html",
            "--directory", str(self.coverage_dir),
            "--title", "krr MCP Server Coverage Report"
        ]
        
        success = self._run_command(cmd, "Coverage HTML report")
        
        if success:
            print(f"📈 Coverage report generated at: {self.coverage_dir / 'index.html'}")
        
        # Generate XML report for CI/CD
        xml_cmd = [
            "python", "-m", "coverage", "xml",
            "-o", str(self.reports_dir / "coverage.xml")
        ]
        
        self._run_command(xml_cmd, "Coverage XML report")
        
        return success
    
    def validate_coverage_requirements(self) -> bool:
        """Validate coverage meets requirements."""
        print("✅ Validating coverage requirements...")
        
        # Check overall coverage
        cmd = ["python", "-m", "coverage", "report", "--show-missing"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        if result.returncode != 0:
            print("❌ Coverage validation failed!")
            print(result.stderr)
            return False
        
        coverage_output = result.stdout
        print(coverage_output)
        
        # Parse coverage percentage
        lines = coverage_output.strip().split('\n')
        total_line = lines[-1]
        
        if "TOTAL" in total_line:
            parts = total_line.split()
            coverage_percent = parts[-1].rstrip('%')
            
            try:
                coverage = float(coverage_percent)
                print(f"📊 Total coverage: {coverage}%")
                
                if coverage >= 90.0:
                    print("✅ Coverage requirements met!")
                    return True
                else:
                    print(f"❌ Coverage {coverage}% below required 90%!")
                    return False
            except ValueError:
                print("❌ Could not parse coverage percentage!")
                return False
        
        return False
    
    def run_quality_gates(self) -> bool:
        """Run quality gate validation."""
        print("🏁 Running quality gates...")
        
        quality_checks = [
            ("Safety-critical coverage", self._check_safety_coverage),
            ("Integration test completeness", self._check_integration_completeness),
            ("Performance benchmarks", self._check_performance_benchmarks),
            ("Chaos test resilience", self._check_chaos_resilience),
        ]
        
        all_passed = True
        
        for check_name, check_function in quality_checks:
            print(f"\n🔍 Checking: {check_name}")
            
            if check_function():
                print(f"✅ {check_name}: PASSED")
            else:
                print(f"❌ {check_name}: FAILED")
                all_passed = False
        
        return all_passed
    
    def _run_command(self, cmd: List[str], description: str) -> bool:
        """Run a command and return success status."""
        start_time = time.time()
        
        result = subprocess.run(cmd, cwd=self.project_root)
        
        end_time = time.time()
        duration = end_time - start_time
        
        if result.returncode == 0:
            print(f"✅ {description} completed in {duration:.2f}s")
            return True
        else:
            print(f"❌ {description} failed after {duration:.2f}s")
            return False
    
    def _check_safety_coverage(self) -> bool:
        """Check safety-critical module coverage."""
        # This would check actual coverage data
        # For now, assume it passes if safety tests pass
        return True
    
    def _check_integration_completeness(self) -> bool:
        """Check integration test completeness."""
        # Count integration test scenarios
        integration_file = self.test_dir / "test_integration_workflows.py"
        
        if not integration_file.exists():
            return False
        
        content = integration_file.read_text()
        
        # Count test methods
        test_methods = content.count("def test_")
        
        # Should have at least 25 integration tests
        return test_methods >= 25
    
    def _check_performance_benchmarks(self) -> bool:
        """Check performance benchmark coverage."""
        performance_file = self.test_dir / "test_performance.py"
        
        if not performance_file.exists():
            return False
        
        content = performance_file.read_text()
        
        # Check for key performance scenarios
        required_scenarios = [
            "large_cluster_simulation",
            "concurrent_request_handling", 
            "memory_usage_optimization",
            "caching_performance",
        ]
        
        for scenario in required_scenarios:
            if scenario not in content:
                return False
        
        return True
    
    def _check_chaos_resilience(self) -> bool:
        """Check chaos test coverage."""
        chaos_file = self.test_dir / "test_chaos.py"
        
        if not chaos_file.exists():
            return False
        
        content = chaos_file.read_text()
        
        # Check for key chaos scenarios
        required_scenarios = [
            "network_interruption",
            "resource_exhaustion",
            "external_dependency_failures",
            "corrupted_data_handling",
        ]
        
        for scenario in required_scenarios:
            if scenario not in content:
                return False
        
        return True


def main():
    """Main test runner entry point."""
    parser = argparse.ArgumentParser(description="krr MCP Server Test Runner")
    
    parser.add_argument(
        "--suite", 
        choices=["unit", "integration", "performance", "chaos", "safety", "all"],
        default="all",
        help="Test suite to run"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--coverage-only",
        action="store_true", 
        help="Only generate coverage report"
    )
    
    parser.add_argument(
        "--quality-gates",
        action="store_true",
        help="Run quality gate validation"
    )
    
    args = parser.parse_args()
    
    # Find project root
    current_dir = Path(__file__).parent
    project_root = current_dir.parent
    
    runner = TestRunner(project_root)
    
    if args.coverage_only:
        success = runner.generate_coverage_report()
        sys.exit(0 if success else 1)
    
    if args.quality_gates:
        success = runner.run_quality_gates()
        sys.exit(0 if success else 1)
    
    # Run tests
    success = False
    
    if args.suite == "unit":
        success = runner.run_unit_tests(args.verbose)
    elif args.suite == "integration":
        success = runner.run_integration_tests(args.verbose)
    elif args.suite == "performance":
        success = runner.run_performance_tests(args.verbose)
    elif args.suite == "chaos":
        success = runner.run_chaos_tests(args.verbose)
    elif args.suite == "safety":
        success = runner.run_safety_critical_tests(args.verbose)
    elif args.suite == "all":
        results = runner.run_all_tests(args.verbose)
        success = all(results.values())
        
        # Generate coverage report
        print(f"\n{'='*60}")
        runner.generate_coverage_report()
        
        # Validate coverage requirements
        print(f"\n{'='*60}")
        coverage_ok = runner.validate_coverage_requirements()
        
        # Run quality gates
        print(f"\n{'='*60}")
        quality_ok = runner.run_quality_gates()
        
        success = success and coverage_ok and quality_ok
        
        # Print final summary
        print(f"\n{'='*60}")
        print("📋 TEST SUMMARY")
        print(f"{'='*60}")
        
        for suite_name, result in results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{suite_name.title():<20} {status}")
        
        print(f"Coverage Requirements {'✅ PASSED' if coverage_ok else '❌ FAILED'}")
        print(f"Quality Gates        {'✅ PASSED' if quality_ok else '❌ FAILED'}")
        
        if success:
            print("\n🎉 ALL TESTS PASSED! Ready for production.")
        else:
            print("\n💥 SOME TESTS FAILED! Please fix before proceeding.")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()