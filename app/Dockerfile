# syntax=docker/dockerfile:1

FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.11.14

# 의존성 파일을 먼저 복사해 소스 변경 시에도 Docker layer cache를 활용한다.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra app


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app

COPY --from=builder /opt/venv /opt/venv
COPY app /app/app
COPY static /app/static
COPY alembic /app/alembic
COPY alembic.ini pyproject.toml uv.lock /app/

RUN mkdir -p /app/media/uploads/xray /app/media/uploads/heatmaps \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl --fail http://localhost:8000/healthcheck || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
