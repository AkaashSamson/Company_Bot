# ==============================================================================
# Multi-Stage Dockerfile for KnowLayer (FastAPI Backend & Streamlit Frontend)
# ==============================================================================
# ARCHITECTURE:
# This Dockerfile produces two distinct, optimized production images:
#   1. Target `frontend`: Minimal Streamlit UI (~180 MB) without heavy ML packages.
#   2. Target `backend`:  Modular Monolith FastAPI API (~1.3 GB) with PyTorch CPU,
#                         Docling, ChromaDB, and document processing libraries.
#
# USAGE:
#   docker build --target frontend -t knowlayer-frontend:latest .
#   docker build --target backend  -t knowlayer-backend:latest .
#   Or simply run via docker-compose: docker compose up --build
# ==============================================================================

# ==============================================================================
# STAGE 1: BASE IMAGE
# ==============================================================================
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# ==============================================================================
# STAGE 2: STREAMLIT FRONTEND TARGET (~180 MB)
# ==============================================================================
FROM base AS frontend

# Install curl for container health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install lightweight presentation dependencies via uv
RUN pip install --no-cache-dir uv
COPY requirements-frontend.txt .
RUN uv pip install --system --no-cache -r requirements-frontend.txt

# Copy Streamlit configuration and presentation code
COPY .streamlit/ ./.streamlit/
COPY streamlit_app/ ./streamlit_app/

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "streamlit_app/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]

# ==============================================================================
# STAGE 3: FASTAPI MODULAR MONOLITH BACKEND TARGET (~1.3 GB)
# ==============================================================================
FROM base AS backend

# Install Linux system dependencies:
# - curl: healthcheck probes
# - build-essential: gcc/g++ compilers for C-extensions
# - libgl1, libglib2.0-0: required at runtime by OpenCV and EasyOCR
# - poppler-utils: PDF rendering and page extraction fallbacks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install uv for high-speed multi-threaded parallel downloads
RUN pip install --no-cache-dir uv

# Pre-install PyTorch CPU wheel explicitly via uv (prevents multi-gigabyte CUDA downloads)
RUN uv pip install --system --no-cache --extra-index-url https://download.pytorch.org/whl/cpu "torch>=2.2"

# Install backend dependencies in parallel via uv
COPY requirements-backend.txt .
RUN uv pip install --system --no-cache --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-backend.txt

# Pre-create runtime directories for persistent volumes
RUN mkdir -p /app/instance \
             /app/.chroma \
             /app/conversation_logs \
             /app/cache \
             /app/data \
             /app/input

# Copy application domain, config, and seed data
COPY app/ ./app/
COPY config/ ./config/
COPY data/ ./data/
COPY input/ ./input/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
