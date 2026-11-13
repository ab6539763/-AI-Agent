"""Entrypoint for Project P02 Healthcare & Clinical Decision Support Copilot."""

from __future__ import annotations

import os

import uvicorn

from app.api import app


def main() -> None:
    host = os.environ.get("P02_HOST", "0.0.0.0")
    port = int(os.environ.get("P02_PORT", "8000"))
    log_level = os.environ.get("P02_LOG_LEVEL", "info")
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
