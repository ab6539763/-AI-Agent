"""Entrypoint for running the P07 DevSecOps Copilot API server."""

from __future__ import annotations

import os
import uvicorn

from app.api import app


def main() -> None:
    host = os.environ.get("P07_HOST", "0.0.0.0")
    port = int(os.environ.get("P07_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
