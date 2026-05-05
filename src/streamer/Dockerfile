# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

RUN pip install uv --no-cache-dir

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-default-groups --group streamer

COPY src/streamer/ ./src/streamer/

EXPOSE 8001
CMD ["uv", "run", "python", "src/streamer/main.py"]
