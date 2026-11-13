# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir fastapi uvicorn pydantic httpx

# Stage 2: Runtime (non-root)
FROM python:3.12-slim AS runtime

RUN groupadd --gid 10001 devsecops \
    && useradd --uid 10001 --gid devsecops --shell /bin/false --create-home devsecops

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app/ ./app/
COPY main.py ./main.py

RUN mkdir -p /data/wiki && chown -R devsecops:devsecops /app /data/wiki

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    P07_HOST=0.0.0.0 \
    P07_PORT=8080 \
    P07_WIKI_DIR=/data/wiki

USER devsecops
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

CMD ["python", "main.py"]
