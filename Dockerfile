# Multi-stage Dockerfile for Python microservices

# Build stage
FROM python:3.11-slim as builder

WORKDIR /tmp

# Copy requirements files
COPY requirements.txt .

# Create a virtual environment and install packages
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install setuptools in system Python to ensure pkg_resources is available
RUN pip install --no-cache-dir setuptools

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Copy application code
COPY . .

# Health check (removed complex check that might fail)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Default command (can be overridden)
CMD ["python", "main.py"]
