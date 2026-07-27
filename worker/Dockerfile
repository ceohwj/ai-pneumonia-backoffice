# syntax=docker/dockerfile:1

FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.14

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra ai


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MEDIA_ROOT=/app/media

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system worker \
    && useradd --system --gid worker --home-dir /app worker

COPY --from=builder /opt/venv /opt/venv
COPY worker /app/worker

RUN mkdir -p /app/media/uploads/heatmaps \
    && chown -R worker:worker /app

USER worker

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "from worker.redis_client import redis_client; assert redis_client.ping()" || exit 1

CMD ["python", "-m", "worker.main"]
