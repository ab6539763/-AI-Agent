"""CLI & Uvicorn entrypoint for Project P04: Smart Manufacturing Ops Agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

# Ensure project root is on sys.path when executed directly
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


def main() -> None:
    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = int(os.environ.get("APP_PORT", "8000"))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    uvicorn.run("app.api:app", host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
