# Akaash — Deployment

## Role Overview
Project lead and owner of everything that gets KnowLayer from "runs on one laptop via `setup.ps1`" to a reliably deployed, observable, cost-controlled service — currently a local FastAPI + Streamlit + Chroma setup, with a defined path to cloud deployment.

## Core Responsibilities
- **Environment & setup tooling** — `setup.ps1`, `.env` management, dependency installation (`requirements.txt`).
- **Service orchestration** — running FastAPI (`app/main.py`, port 8000/8001) and Streamlit (`streamlit_app/app.py`, port 8501) together, locally and eventually in the cloud.
- **Deployment path** — executing the roadmap's move from local `.chroma/` + local files to managed infrastructure: FastAPI → Cloud Run/ECS, Streamlit → Streamlit Cloud/Docker, Chroma → Pinecone/Weaviate, documents → S3/GCS.
- **Observability** — structured logging, audit trails, and health checks (`/health`) becoming real production monitoring.
- **Secrets & configuration** — API keys (`OPENROUTER_API_KEY`, `GROQ_API_KEY`, future `DATABASE_URL`, `JWT_SECRET`) handled safely across environments (dev/staging/prod).
- **Release process** — as the project grows past a single MVP script, defining how builds, tests, and deploys actually happen.

## Current System Touchpoints
- `setup.ps1`, `requirements.txt`, `.env`
- `app/main.py` (FastAPI entrypoint, health endpoint)
- `app/core/settings.py` (environment-backed config)
- `.chroma/` (local persistent vector store — first thing to outgrow)

## Research Topics to Improve Efficiency

1. **Containerization strategy** — Dockerize FastAPI and Streamlit as separate services with a `docker-compose` for local dev, as a stepping stone to Cloud Run/ECS/K8s.
2. **Managed vector DB migration** — compare Pinecone vs Weaviate Cloud vs a self-hosted `pgvector` (pairs naturally with the planned PostgreSQL) on cost, latency, and operational overhead for this document volume.
3. **CI/CD pipeline** — automated test runs (`tests/unit`, `tests/contract`, `tests/integration`, `scripts/smoke_test.py`) and deploys on merge, replacing manual `setup.ps1` runs.
4. **Secrets management** — moving from `.env` files to a proper secrets store (cloud provider secrets manager / vault) before real API keys and `JWT_SECRET` exist.
5. **Cost monitoring for LLM calls** — once OpenRouter/Groq are live, track token usage and cost per query so RAG changes ([Abhinav](Abhinav.md)'s work) don't silently blow up spend.
6. **Autoscaling & cold-start latency** — the embedding model download and Chroma load are currently slow on first run; figure out what that looks like under Cloud Run's scale-to-zero model.
7. **Zero-downtime deploys / re-ingestion** — how document re-ingestion (`scripts/ingest_documents.py`) can run without taking the chat service offline once documents are hosted centrally.
8. **Production security hardening** — HTTPS, network isolation between FastAPI and the vector DB, and audit-log storage/retention once auth ([Roshan](Roshan.md)) lands.

## Coordination Notes
- Any infra change to the vector store or document storage must preserve the `RetrievalService`/`ChromaVectorStore` interface boundary so [Abhinav](Abhinav.md) and [Neha](Neha.md)'s code doesn't need to change.
- Auth/JWT/DB deployment needs coordinate closely with [Roshan](Roshan.md)'s backend design before infra is provisioned.
