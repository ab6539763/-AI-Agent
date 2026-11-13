# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi uvicorn pydantic httpx

# Stage 2: Runtime (non-root)
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    P05_DATA_DIR="/app/data" \
    P05_PORT="8005"

RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/false --create-home appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app/ /app/app/
COPY main.py /app/main.py

RUN mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser
EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8005/health')" || exit 1

CMD ["python", "main.py"]
