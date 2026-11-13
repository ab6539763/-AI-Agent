"""Entrypoint for Project P03: Legal Compliance & Contract Review Agent."""

from __future__ import annotations

import argparse
import json
import os
import uvicorn

from app.api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P03 Legal Compliance & Contract Review Agent")
    parser.add_argument("--host", default=os.environ.get("APP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("APP_PORT", "8000")))
    parser.add_argument("--wiki-dir", default=os.environ.get("WIKI_DIR", "./data/legal_wiki"))
    parser.add_argument("--check", action="store_true", help="Run offline self-check and exit")
    args = parser.parse_args()

    application = create_app(wiki_dir=args.wiki_dir)
    if args.check:
        summary = {
            "status": "ok",
            "regulations": len(application.state.registry.regulations),
            "wiki_dir": str(application.state.wiki.root_dir),
        }
        print(json.dumps(summary, indent=2))
        return

    uvicorn.run(application, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
