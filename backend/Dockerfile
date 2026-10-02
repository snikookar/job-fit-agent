# Build from the repo root:  docker build -f backend/Dockerfile .
# Real embeddings/reranker:  docker build -f backend/Dockerfile --build-arg EXTRAS="--extra ml" .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend
ARG EXTRAS=""

# Dependencies first, so code changes don't invalidate this layer.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project ${EXTRAS}

COPY backend/ ./
COPY sample_profile/ /app/sample_profile/
RUN uv sync --frozen --no-dev ${EXTRAS}

ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "jobfit.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
