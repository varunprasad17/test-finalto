# Root Dockerfile — not used directly by docker compose.
# Each service has its own Dockerfile under src/<service>/Dockerfile.
# This file exists as a reference / single-image build for CI or quick local runs.
#
# Build:  docker build -t finalto-risk .
# (Does not run any service on its own — use docker compose instead.)

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
