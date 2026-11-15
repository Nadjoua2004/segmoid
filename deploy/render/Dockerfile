# Aegis-Bio backend + AstroDoc AI on Render (free web service: 512 MB RAM, 0.1 CPU).
# Build context: the repository root (Render "Docker Build Context Directory" = .), so the folder layout
# matches the repo and the backend finds AstroDoc at ../../astrodoc/backend.
#
# Memory (measured): ~380 MB steady, ~385 MB peak with ChromaDB semantic search. The embedding model is
# loaded once and shared by AstroDoc and the backend (astrodoc/backend/app/knowledge/retriever.py).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2

WORKDIR /app
COPY deploy/render/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY aegis-bio/backend /app/aegis-bio/backend
COPY astrodoc/backend /app/astrodoc/backend

# AstroDoc knowledge base: download the embedding model (all-MiniLM-L6-v2, ~80 MB) and build the Chroma
# index into the image, so the server never downloads anything when it starts.
RUN cd /app/astrodoc/backend && python -m app.knowledge.ingest

# Production defaults. Secrets (LLM_API_KEY, DATABASE_URL, SECRET_KEY) and FRONTEND_ORIGINS are set in
# the Render dashboard, never in this file.
ENV DEBUG=false \
    ASTRODOC_RETRIEVER=chroma \
    LLM_BASE_URL=https://api.groq.com/openai/v1 \
    LLM_MODEL=openai/gpt-oss-120b \
    LLM_FALLBACK_MODELS=openai/gpt-oss-20b,qwen/qwen3.8-27b \
    LLM_HELPER_MODEL=openai/gpt-oss-20b \
    LLM_VISION_MODEL=qwen/qwen3.8-27b \
    LLM_REASONING_EFFORT=low

WORKDIR /app/aegis-bio/backend
# Render gives the port in $PORT (10000 by default)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips '*'"]
