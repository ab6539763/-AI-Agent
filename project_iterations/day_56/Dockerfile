# syntax=docker/dockerfile:1
# ==============================================================================
# 智枢企业级智能体平台 (ZhiShu-Agent) · Day 56 生产级多阶段 Dockerfile
# 版本: v0.5.0-day56
# 特性: Python 3.11-slim + 多阶段构建 + 非 root 用户运行 + 内置 HEALTHCHECK
# ==============================================================================

# ---------- Stage 1: Builder (编译与依赖安装) ----------
FROM python:3.11-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装生产运行时依赖（无构建工具链污染最终镜像）
RUN pip install --upgrade pip && \
    pip install fastapi==0.115.0 uvicorn[standard]==0.30.6 pydantic==2.9.2 \
                qdrant-client==1.11.3 redis==5.1.1 httpx==0.27.2


# ---------- Stage 2: Runtime (最小化生产运行镜像) ----------
FROM python:3.11-slim AS runtime

LABEL maintainer="ZhiShu DevOps <devops@zhishu-agent.local>" \
      version="v0.5.0-day56" \
      description="ZhiShu-Agent FastAPI Production Service"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_HOME=/app

# 创建最小权限非 root 用户与用户组
RUN groupadd --system --gid 10001 zhishu && \
    useradd --system --uid 10001 --gid zhishu --create-home --shell /usr/sbin/nologin zhishu

WORKDIR /app

# 仅从 builder 复制虚拟环境，大幅缩减镜像体积
COPY --from=builder /opt/venv /opt/venv

# 复制应用代码并设置目录归属
COPY --chown=zhishu:zhishu . /app

# 创建持久化数据与日志挂载目录
RUN mkdir -p /app/data /app/logs && \
    chown -R zhishu:zhishu /app/data /app/logs

# 切换为非 root 用户运行
USER zhishu

EXPOSE 8000

# 容器级健康检查：探测 FastAPI /health 端点
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "zhishu_agent.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
