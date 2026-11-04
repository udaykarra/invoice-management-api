# Multi-stage reproducible container image for Invoice Management API
FROM python:3.11-slim AS runtime

# Set environment flags
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# Install system dependencies for PostgreSQL client and health probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Install pinned Python dependencies with cryptographic hash verification
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --require-hashes -r requirements.lock

# Copy application source code
COPY app/ ./app/
COPY README.md .

# Create persistent storage directory for SQLite WAL databases
RUN mkdir -p /app/data && chown -R appuser:appgroup ${APP_HOME}

# Switch to non-root user
USER appuser

# Expose standard application port
EXPOSE 8000

# Docker native healthcheck probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI application with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

