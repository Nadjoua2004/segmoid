# Aegis-Bio backend + AstroDoc AI as a Hugging Face Docker Space.
# Built by deploy/huggingface/deploy_space.py, which copies aegis-bio/backend and astrodoc/backend
# next to this file with the same folder layout as the repo (the backend finds AstroDoc at ../../astrodoc).
FROM python:3.11-slim

# Hugging Face runs Space containers as uid 1000
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY --chown=user aegis-bio/backend /app/aegis-bio/backend
COPY --chown=user astrodoc/backend /app/astrodoc/backend
RUN chown user /app
USER user

# AstroDoc knowledge base: download the embedding model and build the Chroma index into the image,
# so the server never downloads anything at startup.
RUN cd /app/astrodoc/backend && python -m app.knowledge.ingest

# Production defaults; secrets (LLM_API_KEY, DATABASE_URL, SECRET_KEY ...) come from the Space settings.
ENV DEBUG=false \
    HOST=0.0.0.0 \
    PORT=7860 \
    LLM_BASE_URL=https://api.groq.com/openai/v1 \
    LLM_MODEL=openai/gpt-oss-120b \
    LLM_FALLBACK_MODELS=openai/gpt-oss-20b,qwen/qwen3.8-27b \
    LLM_HELPER_MODEL=openai/gpt-oss-20b \
    LLM_VISION_MODEL=qwen/qwen3.8-27b \
    LLM_REASONING_EFFORT=low

WORKDIR /app/aegis-bio/backend
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
