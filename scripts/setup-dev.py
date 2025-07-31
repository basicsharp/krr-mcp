#!/usr/bin/env python3
"""
Development environment setup script for KRR MCP Server.

This script sets up the development environment with all necessary dependencies,
tools, and configurations for contributing to the project.
"""

import os
import platform
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
        if check:
            raise
        return e


def check_python_version() -> bool:
    """Check if Python 3.12+ is available."""
    print("🐍 Checking Python version...")

    version = sys.version_info
    if version.major == 3 and version.minor >= 12:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} is suitable")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} is too old")
        print("Please install Python 3.12 or later")
        return False


def check_uv_installation() -> bool:
    """Check if uv is installed and install if necessary."""
    print("📦 Checking uv installation...")

    try:
        result = run_command(["uv", "--version"], check=False)
        if result.returncode == 0:
            print("✅ uv is already installed")
            return True
    except FileNotFoundError:
        pass

    print("Installing uv...")

    # Install uv using the official installer
    try:
        if platform.system() == "Windows":
            # Windows installation
            run_command(
                ["powershell", "-c", "irm https://astral.sh/uv/install.ps1 | iex"]
            )
        else:
            # Unix-like systems
            run_command(["curl", "-LsSf", "https://astral.sh/uv/install.sh"])
            run_command(["sh", "-"])
    except Exception as e:
        print(f"❌ Failed to install uv: {e}")
        print(
            "Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
        )
        return False

    print("✅ uv installed successfully")
    return True


def setup_virtual_environment(project_root: Path) -> bool:
    """Set up the virtual environment and install dependencies."""
    print("🏗️  Setting up virtual environment...")

    try:
        # Sync all dependencies including dev dependencies
        run_command(["uv", "sync", "--all-extras"], cwd=project_root)
        print("✅ Virtual environment set up successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to set up virtual environment: {e}")
        return False


def install_external_tools() -> bool:
    """Install external tools required for development."""
    print("🔧 Checking external tools...")

    tools_status = []

    # Check kubectl
    try:
        run_command(["kubectl", "version", "--client"], check=False)
        print("✅ kubectl is available")
        tools_status.append(True)
    except FileNotFoundError:
        print("⚠️  kubectl not found. Please install kubectl for Kubernetes integration")
        print("   Installation: https://kubernetes.io/docs/tasks/tools/")
        tools_status.append(False)

    # Check Docker
    try:
        run_command(["docker", "--version"], check=False)
        print("✅ Docker is available")
        tools_status.append(True)
    except FileNotFoundError:
        print("⚠️  Docker not found. Please install Docker for container development")
        print("   Installation: https://docs.docker.com/get-docker/")
        tools_status.append(False)

    # Check kind (optional)
    try:
        run_command(["kind", "version"], check=False)
        print("✅ kind is available")
        tools_status.append(True)
    except FileNotFoundError:
        print("⚠️  kind not found. Install for local Kubernetes testing")
        print("   Installation: https://kind.sigs.k8s.io/docs/user/quick-start/")
        tools_status.append(False)

    return any(tools_status)  # At least some tools should be available


def setup_pre_commit_hooks(project_root: Path) -> bool:
    """Set up pre-commit hooks."""
    print("🪝 Setting up pre-commit hooks...")

    pre_commit_config = project_root / ".pre-commit-config.yaml"
    if not pre_commit_config.exists():
        print("⚠️  .pre-commit-config.yaml not found, skipping pre-commit setup")
        return True

    try:
        # Install pre-commit hooks
        run_command(["uv", "run", "pre-commit", "install"], cwd=project_root)
        print("✅ Pre-commit hooks installed")
        return True
    except Exception as e:
        print(f"⚠️  Failed to install pre-commit hooks: {e}")
        return False


def run_initial_tests(project_root: Path) -> bool:
    """Run a basic test to verify the setup."""
    print("🧪 Running initial tests...")

    try:
        # Run a subset of fast tests
        result = run_command(
            ["uv", "run", "pytest", "tests/test_safety_models.py", "-v", "--tb=short"],
            cwd=project_root,
            check=False,
        )

        if result.returncode == 0:
            print("✅ Initial tests passed")
            return True
        else:
            print("⚠️  Some tests failed, but setup is complete")
            return True
    except Exception as e:
        print(f"⚠️  Failed to run tests: {e}")
        return False


def create_env_file(project_root: Path) -> None:
    """Create a local .env file from template."""
    env_file = project_root / ".env"
    env_docker_file = project_root / ".env.docker"

    if not env_file.exists() and env_docker_file.exists():
        print("📝 Creating .env file from template...")

        with open(env_docker_file, "r") as src:
            content = src.read()

        # Customize for local development
        content = content.replace("LOG_LEVEL=INFO", "LOG_LEVEL=DEBUG")
        content = content.replace("SERVER_PORT=8080", "SERVER_PORT=8080")

        with open(env_file, "w") as dst:
            dst.write(content)

        print("✅ Created .env file for local development")


def print_next_steps(project_root: Path) -> None:
    """Print next steps for the developer."""
    print("\n🎉 Development environment setup complete!")
    print("\n📋 Next steps:")
    print("1. Activate the environment:")
    print(f"   cd {project_root}")
    print("   source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate")
    print("\n2. Run the full test suite:")
    print("   uv run pytest")
    print("\n3. Start developing:")
    print("   uv run python -m src.server --help")
    print("\n4. Build the package:")
    print("   python scripts/build.py")
    print("\n5. Set up a test cluster (optional):")
    print("   kind create cluster --name krr-test --config tests/kind-config.yaml")
    print("   python tests/cluster_manager.py setup")
    print("\n📚 Documentation:")
    print("   - User Guide: docs/user-guide.md")
    print("   - API Reference: docs/api/")
    print("   - Contributing: README.md")
    print("\n🔧 Useful commands:")
    print("   uv run pytest tests/           # Run all tests")
    print("   uv run black src tests/        # Format code")
    print("   uv run flake8 src tests/       # Lint code")
    print("   uv run mypy src/               # Type check")


def main():
    """Main setup script entry point."""
    print("🚀 KRR MCP Server - Development Environment Setup")
    print("=" * 50)

    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    success = True

    # Check prerequisites
    if not check_python_version():
        success = False

    if not check_uv_installation():
        success = False

    if not success:
        print("\n❌ Prerequisites not met. Please fix the issues above and try again.")
        sys.exit(1)

    # Set up development environment
    steps = [
        ("Virtual Environment", lambda: setup_virtual_environment(project_root)),
        ("External Tools", lambda: install_external_tools()),
        ("Pre-commit Hooks", lambda: setup_pre_commit_hooks(project_root)),
        (
            "Environment File",
            lambda: create_env_file(project_root) is None,
        ),  # Always succeeds
        ("Initial Tests", lambda: run_initial_tests(project_root)),
    ]

    for step_name, step_func in steps:
        print(f"\n📋 {step_name}...")
        try:
            if not step_func():
                print(f"⚠️  {step_name} completed with warnings")
        except Exception as e:
            print(f"❌ {step_name} failed: {e}")
            success = False

    if success:
        print_next_steps(project_root)
    else:
        print("\n⚠️  Setup completed with some issues. Check the warnings above.")
        print("The development environment should still be usable.")

    print(
        f"\n🏁 Setup {'completed successfully' if success else 'completed with warnings'}!"
    )


if __name__ == "__main__":
    main()
