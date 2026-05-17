from __future__ import annotations

import argparse

import uvicorn

from .app import create_app
from .core.config import get_settings
from .db.init import create_database

app = create_app()


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the Mianotes web service.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init-db", help="Create database tables for the configured database.")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", default=settings.port, type=int)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if args.command == "init-db":
        create_database()
        return

    uvicorn.run(
        "mianotes_web_service.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
