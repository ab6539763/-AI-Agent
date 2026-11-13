"""Entrypoint for Project P06: 政务服务与企业政策通智能体."""

from __future__ import annotations

import os
import uvicorn

from projects.p06_govtech_policy.app.api import app


def main() -> None:
    host = os.getenv("GOVTECH_HOST", "0.0.0.0")
    port = int(os.getenv("GOVTECH_PORT", "8006"))
    log_level = os.getenv("GOVTECH_LOG_LEVEL", "info")
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
