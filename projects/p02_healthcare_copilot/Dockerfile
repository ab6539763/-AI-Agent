# Multi-stage production Dockerfile for P02 Healthcare Copilot
FROM python:3.11-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn>=0.30.0 \
    pydantic>=2.9.0 \
    httpx>=0.27.0


FROM python:3.11-slim AS runtime

RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /usr/sbin/nologin --create-home appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    P02_HOST=0.0.0.0 \
    P02_PORT=8000 \
    P02_WIKI_DIR=/app/data/wiki \
    P02_AUDIT_LOG_PATH=/app/data/audit.jsonl

COPY --chown=appuser:appgroup app/ /app/app/
COPY --chown=appuser:appgroup main.py /app/main.py

RUN mkdir -p /app/data/wiki && chown -R appuser:appgroup /app/data

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["python", "main.py"]
