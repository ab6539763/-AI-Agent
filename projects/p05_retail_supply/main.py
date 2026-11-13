"""Entrypoint for Project P05: Retail & Supply Chain Growth Agent."""

from __future__ import annotations

import os
import uvicorn

from app.api import app


def main() -> None:
    host = os.environ.get("P05_HOST", "0.0.0.0")
    port = int(os.environ.get("P05_PORT", "8005"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
