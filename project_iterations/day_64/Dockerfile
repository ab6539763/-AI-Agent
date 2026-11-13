# ============================================================================
# 星辰数科 · 智枢企业级智能体平台 (ZhiShu-Agent) v1.0.0-day64
# 生产级多阶段构建 Dockerfile（Multi-stage Build + 非 root 安全基线）
# ============================================================================

# ---------- Stage 1: Builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --prefix=/install \
    fastapi==0.115.0 \
    uvicorn[standard]==0.30.6 \
    pydantic==2.9.2 \
    httpx==0.27.2

# ---------- Stage 2: Production Runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PORT=8000 \
    WORKERS=4

WORKDIR /app

# 创建非 root 运行用户，满足企业容器安全红线
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app

# 从 builder 阶段拷贝已编译依赖
COPY --from=builder /install /usr/local

# 拷贝应用代码
COPY --chown=appuser:appuser zhishu_agent ./zhishu_agent
COPY --chown=appuser:appuser main.py ./main.py

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "zhishu_agent.release_packager:create_demo_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
