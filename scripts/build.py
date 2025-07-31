#!/usr/bin/env python3
"""
Build script for KRR MCP Server package distribution.

This script handles building the package for various distribution channels:
- PyPI (wheel and source distribution)
- Docker containers
- uvx compatibility testing
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def run_command(
    cmd: List[str], cwd: Optional[Path] = None, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a command and handle errors."""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, cwd=cwd, check=check, capture_output=True, text=True
        )
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        raise


def clean_build_artifacts(project_root: Path) -> None:
    """Clean up build artifacts."""
    print("🧹 Cleaning build artifacts...")

    artifacts = [
        "build",
        "dist",
        "*.egg-info",
        "**/__pycache__",
        "**/*.pyc",
        "**/*.pyo",
    ]

    for pattern in artifacts:
        for path in project_root.glob(pattern):
            if path.is_dir():
                import shutil

                shutil.rmtree(path)
                print(f"Removed directory: {path}")
            else:
                path.unlink()
                print(f"Removed file: {path}")


def build_python_package(project_root: Path, clean: bool = True) -> None:
    """Build Python package for PyPI distribution."""
    print("📦 Building Python package...")

    if clean:
        clean_build_artifacts(project_root)

    # Build with uv
    run_command(["uv", "build"], cwd=project_root)

    # Verify the build
    dist_dir = project_root / "dist"
    if not dist_dir.exists():
        raise RuntimeError("Build failed: dist directory not created")

    wheels = list(dist_dir.glob("*.whl"))
    tarballs = list(dist_dir.glob("*.tar.gz"))

    print(f"✅ Built {len(wheels)} wheel(s) and {len(tarballs)} source distribution(s)")
    for wheel in wheels:
        print(f"  - {wheel.name}")
    for tarball in tarballs:
        print(f"  - {tarball.name}")


def test_uvx_compatibility(project_root: Path) -> None:
    """Test uvx compatibility."""
    print("🧪 Testing uvx compatibility...")

    # Check if uvx is available
    try:
        run_command(["uvx", "--version"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️  uvx not available, skipping compatibility test")
        return

    # Test installation from local wheel
    dist_dir = project_root / "dist"
    wheels = list(dist_dir.glob("*.whl"))

    if not wheels:
        print("⚠️  No wheels found, run build first")
        return

    wheel_path = wheels[0]
    print(f"Testing uvx installation of {wheel_path.name}")

    # Test uvx run
    try:
        result = run_command(
            ["uvx", "--from", str(wheel_path), "krr-mcp-server", "--help"], check=False
        )

        if result.returncode == 0:
            print("✅ uvx compatibility test passed")
        else:
            print("❌ uvx compatibility test failed")
            print(f"Exit code: {result.returncode}")
            if result.stderr:
                print("STDERR:", result.stderr)
    except Exception as e:
        print(f"❌ uvx compatibility test failed: {e}")


def build_docker_image(project_root: Path, tag: str = "krr-mcp-server:latest") -> None:
    """Build Docker image."""
    print(f"🐳 Building Docker image: {tag}")

    # Build arguments
    build_args = [
        "--build-arg",
        f"BUILD_VERSION=0.1.0",
        "--build-arg",
        f"BUILD_DATE={subprocess.check_output(['date', '-Iseconds']).decode().strip()}",
        "--build-arg",
        f"VCS_REF={subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=project_root).decode().strip()}",
    ]

    cmd = ["docker", "build"] + build_args + ["-t", tag, "."]
    run_command(cmd, cwd=project_root)

    print(f"✅ Docker image built: {tag}")


def test_docker_image(tag: str = "krr-mcp-server:latest") -> None:
    """Test Docker image."""
    print(f"🧪 Testing Docker image: {tag}")

    # Test that the image runs and passes health check
    try:
        # Start container in background
        run_command(
            [
                "docker",
                "run",
                "-d",
                "--name",
                "krr-mcp-test",
                "--health-interval=10s",
                "--health-retries=3",
                tag,
            ]
        )

        # Wait for health check
        import time

        time.sleep(30)

        # Check health status
        result = run_command(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                "krr-mcp-test",
            ],
            check=False,
        )

        if result.returncode == 0 and "healthy" in result.stdout:
            print("✅ Docker image health check passed")
        else:
            print("❌ Docker image health check failed")
            # Show logs for debugging
            run_command(["docker", "logs", "krr-mcp-test"], check=False)

    finally:
        # Clean up test container
        run_command(["docker", "rm", "-f", "krr-mcp-test"], check=False)


def run_tests(project_root: Path) -> None:
    """Run the test suite."""
    print("🧪 Running test suite...")

    run_command(["uv", "run", "pytest", "-v", "--tb=short"], cwd=project_root)
    print("✅ All tests passed")


def main():
    """Main build script entry point."""
    parser = argparse.ArgumentParser(
        description="Build KRR MCP Server for distribution"
    )
    parser.add_argument(
        "--clean", action="store_true", help="Clean build artifacts first"
    )
    parser.add_argument("--no-tests", action="store_true", help="Skip running tests")
    parser.add_argument(
        "--python-only", action="store_true", help="Build Python package only"
    )
    parser.add_argument(
        "--docker-only", action="store_true", help="Build Docker image only"
    )
    parser.add_argument(
        "--docker-tag", default="krr-mcp-server:latest", help="Docker image tag"
    )
    parser.add_argument(
        "--test-uvx", action="store_true", help="Test uvx compatibility"
    )
    parser.add_argument("--test-docker", action="store_true", help="Test Docker image")

    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    try:
        # Run tests first (unless skipped)
        if not args.no_tests:
            run_tests(project_root)

        # Build Python package
        if not args.docker_only:
            build_python_package(project_root, clean=args.clean)

            if args.test_uvx:
                test_uvx_compatibility(project_root)

        # Build Docker image
        if not args.python_only:
            build_docker_image(project_root, args.docker_tag)

            if args.test_docker:
                test_docker_image(args.docker_tag)

        print("🎉 Build completed successfully!")

    except Exception as e:
        print(f"❌ Build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
