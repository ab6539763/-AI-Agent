# Multi-stage Dockerfile for Project P01: FinTech Research & Compliance Agent
FROM python:3.11-slim AS builder

WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi uvicorn pydantic httpx


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    P01_DATA_DIR="/app/data" \
    P01_HOST="0.0.0.0" \
    P01_PORT="8000"

RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/false --create-home appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app/ /app/app/
COPY main.py /app/main.py

RUN mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" || exit 1

CMD ["python", "main.py", "--mode", "serve", "--host", "0.0.0.0", "--port", "8000"]
