# Multi-stage production Dockerfile for P06 GovTech Policy Agent
FROM python:3.12-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi uvicorn pydantic httpx

FROM python:3.12-slim AS runtime

RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid 10001 --shell /bin/false --create-home appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GOVTECH_HOST=0.0.0.0 \
    GOVTECH_PORT=8006 \
    GOVTECH_DATA_DIR=/app/data

COPY projects/p06_govtech_policy /app/projects/p06_govtech_policy
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser
EXPOSE 8006

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8006/health', timeout=3)" || exit 1

CMD ["uvicorn", "projects.p06_govtech_policy.app.api:app", "--host", "0.0.0.0", "--port", "8006"]
