# KRR MCP Server - Production Docker Image
# Multi-stage build for optimized production deployment

# Build stage - Install dependencies and build package
FROM python:3.12-slim as builder

# Set build arguments
ARG BUILD_VERSION="0.1.0"
ARG BUILD_DATE
ARG VCS_REF

# Install system dependencies needed for building
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies in virtual environment
RUN uv sync --frozen --no-install-project --no-dev

# Copy source code
COPY src/ ./src/
COPY README.md ./

# Build the wheel
RUN uv build

# Production stage - Minimal runtime image
FROM python:3.12-slim as production

# Set build metadata as labels
LABEL maintainer="KRR MCP Server Team" \
      org.opencontainers.image.title="KRR MCP Server" \
      org.opencontainers.image.description="MCP server for safe Kubernetes resource optimization using krr" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/krr-mcp/krr-mcp-server" \
      org.opencontainers.image.documentation="https://github.com/krr-mcp/krr-mcp-server/blob/main/README.md" \
      org.opencontainers.image.licenses="Apache-2.0"

# Install system dependencies for runtime
RUN apt-get update && apt-get install -y \
    # kubectl dependency
    curl \
    # krr dependencies
    python3-pip \
    # Health check dependencies
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl (detect architecture)
RUN ARCH=$(dpkg --print-architecture) && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/${ARCH}/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

# Install krr (try multiple possible package names)
RUN pip install --no-cache-dir robusta-krr>=1.7.0 || \
    pip install --no-cache-dir krr-cli>=1.7.0 || \
    pip install --no-cache-dir krr>=1.7.0 || \
    echo "Warning: krr not installed via pip. Manual installation may be required."

# Install uv for runtime dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Create non-root user for security
RUN groupadd -r krrmcp && useradd -r -g krrmcp -d /app -s /bin/bash krrmcp

# Set working directory
WORKDIR /app

# Copy built wheel and install it directly with uv
COPY --from=builder /app/dist/*.whl ./
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python --no-cache *.whl && \
    rm -f *.whl

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data && \
    chown -R krrmcp:krrmcp /app

# Copy health check script
COPY --chmod=755 <<'EOF' /app/healthcheck.sh
#!/bin/bash
set -e

# Check if the server is responding on the health endpoint
# For MCP servers, we check if the server process is running and listening
if pgrep -f "krr-mcp-server" > /dev/null; then
    echo "KRR MCP Server is running"
    exit 0
else
    echo "KRR MCP Server is not running"
    exit 1
fi
EOF

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KRR_MCP_LOG_LEVEL=INFO \
    KRR_MCP_LOG_FORMAT=json

# Expose port (MCP servers typically use stdio, but we may add HTTP in future)
EXPOSE 8080

# Switch to non-root user
USER krrmcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD /app/healthcheck.sh

# Default command - run the MCP server
CMD ["/app/.venv/bin/python", "-m", "src.server"]
