# Root Dockerfile — not used by docker compose.
# Reference / single-image build for CI or quick local runs.
# Build:  docker build -t finalto-risk .
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

RUN pip install uv --no-cache-dir

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project \
    --group streamer --group backend --group dashboard

COPY src/ ./src/
