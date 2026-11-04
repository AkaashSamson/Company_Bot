# ==============================================================================
# Dockerfile for KnowLayer (FastAPI Backend & Streamlit Frontend)
# ==============================================================================
# REASONING FOR MULTI-SERVICE SINGLE DOCKERFILE:
# Both FastAPI and Streamlit share the same core Python dependencies (langchain,
# chromadb, pydantic, etc.). Using one shared base image allows Docker to build and
# cache the dependencies once, saving disk space and drastically speeding up builds.
# We then differentiate the service at runtime using `docker-compose.yml` commands.
# ==============================================================================

# BASE IMAGE
# REASONING:
# 1. We choose `python:3.12-slim` instead of `alpine`.
#    Alpine uses `musl libc` which causes compatibility issues with pre-compiled wheels
#    for PyTorch, chromadb, and sentence-transformers (causing massive compile times or failures).
# 2. `slim` uses Debian glibc, ensuring 100% binary compatibility while remaining small (~150MB).
FROM python:3.12-slim

# ENVIRONMENT VARIABLES
# REASONING:
# - PYTHONDONTWRITEBYTECODE=1: Prevents Python from writing .pyc files to disk inside the container.
# - PYTHONUNBUFFERED=1: Forces stdout/stderr to be flushed immediately, ensuring logs stream in real-time.
# - PYTHONPATH=/app: Ensures imports like `from app.core import settings` resolve from the root.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# WORKING DIRECTORY
# REASONING: All subsequent instructions and runtime commands will execute inside `/app`.
WORKDIR /app

# SYSTEM DEPENDENCIES
# REASONING:
# - `curl`: Needed for Docker container healthcheck probes (`curl -f http://localhost:8000/health`).
# - `build-essential`: Provides gcc/g++ compilers needed if any Python package requires C-extension compilation.
# - `--no-install-recommends`: Avoids installing optional packages, keeping image footprint minimal.
# - `rm -rf /var/lib/apt/lists/*`: Cleans the apt cache in the same layer to avoid bloating the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# DOCKER LAYER CACHING: DEPENDENCIES STEP
# REASONING:
# Docker caches each layer. By copying ONLY `requirements.txt` first and running `pip install`,
# Docker reuses this cached layer whenever you change Python code. Pip will ONLY re-run when
# `requirements.txt` actually changes, saving minutes per build.
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# PRE-CREATE RUNTIME DIRECTORIES
# REASONING:
# The application expects these directories to exist for SQLite DB, Chroma vector store,
# uploaded docs, and conversation logs. Pre-creating them ensures proper filesystem permissions
# before persistent Docker volumes are mounted over them.
RUN mkdir -p /app/instance \
             /app/.chroma \
             /app/conversation_logs \
             /app/cache \
             /app/data \
             /app/input

# COPY APPLICATION CODE
# REASONING:
# Source code changes frequently. Placing this step near the bottom ensures only this
# final, lightweight layer rebuilds during iterative feature development.
COPY app/ ./app/
COPY streamlit_app/ ./streamlit_app/
COPY data/ ./data/
COPY input/ ./input/

# EXPOSE PORTS
# REASONING:
# EXPOSE serves as documentation for developers and container orchestrators:
# - 8000: FastAPI backend REST API
# - 8501: Streamlit interactive web frontend
EXPOSE 8000 8501

# DEFAULT RUNTIME COMMAND
# REASONING:
# By default, running this container starts the FastAPI backend.
# When running as the Streamlit UI, `docker-compose.yml` overrides this command.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
