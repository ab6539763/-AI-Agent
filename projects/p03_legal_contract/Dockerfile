# Multi-stage Dockerfile for Project P03: Legal Compliance & Contract Review Agent
FROM python:3.12-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi uvicorn pydantic httpx

FROM python:3.12-slim AS runtime

RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/false --create-home appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WIKI_DIR=/app/data/legal_wiki \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

COPY app/ /app/app/
COPY main.py /app/main.py

RUN mkdir -p /app/data/legal_wiki && chown -R appuser:appgroup /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["python", "main.py"]
