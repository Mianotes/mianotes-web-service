from __future__ import annotations

import argparse

import uvicorn

from .app import create_app
from .core.config import get_settings
from .db.init import create_database
from .db.session import SessionLocal
from .services.storage_migration import migrate_readable_storage_paths

app = create_app()


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the Mianotes web service.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init-db", help="Create database tables for the configured database.")
    subparsers.add_parser(
        "migrate-storage-paths",
        help="Move existing notes into the readable filesystem layout.",
    )
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", default=settings.port, type=int)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if args.command == "init-db":
        create_database()
        return
    if args.command == "migrate-storage-paths":
        with SessionLocal() as session:
            result = migrate_readable_storage_paths(session, data_dir=settings.data_dir)
        print(
            "Storage path migration complete: "
            f"{result.users_updated} users updated, "
            f"{result.notes_updated} notes updated, "
            f"{result.source_files_updated} source files updated, "
            f"{result.files_moved} files moved."
        )
        return

    uvicorn.run(
        "mianotes_web_service.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
