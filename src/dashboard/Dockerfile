# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

RUN pip install uv --no-cache-dir

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-default-groups --group dashboard

COPY src/dashboard/app.py src/dashboard/charts.py ./
COPY src/dashboard/views/ views/

EXPOSE 8501
CMD ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
