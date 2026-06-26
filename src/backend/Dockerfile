# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

RUN pip install uv --no-cache-dir

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-default-groups --group backend

# Flat copy so bare imports (from metrics import ..., from state import ...) resolve
COPY src/backend/ ./

EXPOSE 8000
CMD ["uv", "run", "python", "main.py"]
