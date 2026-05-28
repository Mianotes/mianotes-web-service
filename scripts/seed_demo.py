#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import random
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

AVATAR_SIZE = (200, 200)
DEFAULT_PASSWORD = "mia"
LOCAL_EMAIL_DOMAIN = "mianotes.dev"
UPPERCASE_WORDS = {"api", "llm", "mcp", "ocr"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed Mianotes with demo users and optional documentation notes."
    )
    parser.add_argument(
        "--admin-email",
        required=True,
        help="Email address for the admin user.",
    )
    parser.add_argument(
        "--admin-name",
        default="Federico",
        help="Display name for the admin user.",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help=f"Master password to set. Defaults to {DEFAULT_PASSWORD!r}.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=REPO_ROOT / "docs",
        help="Documentation directory to import.",
    )
    parser.add_argument(
        "--avatars-dir",
        type=Path,
        default=REPO_ROOT.parent.parent / "designs" / "avatars",
        help="Directory containing demo avatar images.",
    )
    parser.add_argument(
        "--demo-user-count",
        type=int,
        default=6,
        help="Number of demo users to create from avatar filenames.",
    )
    parser.add_argument(
        "--random-note-owners",
        action="store_true",
        help="Assign imported documentation notes across the seeded users.",
    )
    parser.add_argument(
        "--users-only",
        action="store_true",
        help="Seed only global users and profile photos, without creating workspace notes.",
    )
    parser.add_argument(
        "--preserve-existing-passwords",
        action="store_true",
        help="Keep passwords for existing users and the existing master password.",
    )
    parser.add_argument(
        "--note-owner-seed",
        type=int,
        default=42,
        help="Seed used when distributing notes across demo users.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Override MIANOTES_DATA_DIR for this seed run.",
    )
    parser.add_argument(
        "--database-url",
        help="Override MIANOTES_DATABASE_URL for this seed run.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the configured data directory and SQLite database before seeding.",
    )
    return parser.parse_args()


def numbered_slug_title(path: Path) -> str:
    stem = re.sub(r"^\d+[-_]*", "", path.stem)
    words = [word for word in re.split(r"[-_]+", stem) if word]
    titled_words = []
    for index, word in enumerate(words):
        if word in UPPERCASE_WORDS:
            titled_words.append(word.upper())
        elif index == 0:
            titled_words.append(word.capitalize())
        else:
            titled_words.append(word)
    return " ".join(titled_words)


def markdown_title_and_body(markdown: str, fallback: str) -> tuple[str, str]:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.removeprefix("# ").strip() or fallback
            body = "\n".join(lines[index + 1 :]).strip()
            return title, body
    return fallback, markdown.strip()


def sqlite_path_from_url(database_url: str | None) -> Path | None:
    if not database_url:
        return None
    url = make_url(database_url)
    if url.drivername != "sqlite" or url.database in {None, ":memory:"}:
        return None
    return Path(url.database)


def reset_storage(settings) -> None:
    database_path = sqlite_path_from_url(settings.database_url)
    if database_path is not None and database_path.exists():
        database_path.unlink()
    if settings.data_dir.exists():
        shutil.rmtree(settings.data_dir)


def save_avatar(data_dir: Path, user_id: str, avatar_path: Path) -> str:
    with Image.open(avatar_path) as source:
        source.load()
        image = ImageOps.fit(source, AVATAR_SIZE, method=Image.Resampling.LANCZOS)
        if image.mode != "RGB":
            background = Image.new("RGB", image.size, "#ffffff")
            if image.mode in {"RGBA", "LA"}:
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image.convert("RGB"))
            image = background

    relative_path = Path(".profiles") / user_id / "avatar-seed.jpg"
    target = data_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="JPEG", quality=90, optimize=True)
    return relative_path.as_posix()


def user_email_for_name(name: str) -> str:
    from mianotes_web_service.services.storage import slugify

    return f"{slugify(name)}@{LOCAL_EMAIL_DOMAIN}"


def upsert_user(
    session,
    *,
    email: str,
    name: str,
    is_admin: bool,
    avatar_path: Path | None,
    data_dir: Path,
):
    from mianotes_web_service.db.models import User
    from mianotes_web_service.services.storage import make_username

    normalized_email = email.strip().lower()
    user = session.scalars(select(User).where(User.email == normalized_email)).one_or_none()
    if user is None:
        user = User(
            email=normalized_email,
            name=name,
            username=make_username(normalized_email, name),
            is_admin=is_admin,
        )
        session.add(user)
        session.flush()
    else:
        user.name = name
        user.username = make_username(normalized_email, name)
        user.is_admin = user.is_admin or is_admin

    if avatar_path is not None:
        user.avatar_path = save_avatar(data_dir, user.id, avatar_path)
    return user


def seed_users(
    session,
    *,
    admin_email: str,
    admin_name: str,
    password: str,
    avatars_dir: Path,
    count: int,
    data_dir: Path,
    preserve_existing_passwords: bool = False,
):
    from mianotes_web_service.services.auth import (
        get_master_password_hash,
        set_master_password,
        set_user_password,
    )

    admin = upsert_user(
        session,
        email=admin_email,
        name=admin_name,
        is_admin=True,
        avatar_path=None,
        data_dir=data_dir,
    )
    if not preserve_existing_passwords or not admin.password_hash:
        set_user_password(admin, password)
    demo_users = []
    avatar_paths = sorted(
        path
        for path in avatars_dir.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )[:count]
    for avatar_path in avatar_paths:
        name = avatar_path.stem.strip()
        demo_user = upsert_user(
            session,
            email=user_email_for_name(name),
            name=name,
            is_admin=False,
            avatar_path=avatar_path,
            data_dir=data_dir,
        )
        if not preserve_existing_passwords or not demo_user.password_hash:
            set_user_password(demo_user, password)
        demo_users.append(demo_user)
    if not preserve_existing_passwords or get_master_password_hash(session) is None:
        set_master_password(session, password)
    return admin, demo_users


def seed_docs(
    session,
    *,
    owner,
    note_owners,
    docs_dir: Path,
    data_dir: Path,
    note_owner_seed: int,
) -> tuple[int, int]:
    from mianotes_web_service.db.models import Folder, Note, SourceFile, new_id
    from mianotes_web_service.services.storage import (
        FilesystemStorage,
        note_stem,
        render_markdown_note,
        slugify,
        summarize_text,
    )

    storage = FilesystemStorage(data_dir)
    folder_count = 0
    note_count = 0
    doc_folders = [
        folder
        for folder in sorted(docs_dir.iterdir())
        if folder.is_dir() and re.match(r"^\d+", folder.name)
    ]
    owner_pool = list(note_owners) or [owner]
    randomize_note_owners = len(owner_pool) > 1
    rng = random.Random(note_owner_seed)
    rng.shuffle(owner_pool)
    owner_index = 0

    def next_note_owner():
        nonlocal owner_index
        if not randomize_note_owners:
            return owner
        if owner_index > 0 and owner_index % len(owner_pool) == 0:
            rng.shuffle(owner_pool)
        selected_owner = owner_pool[owner_index % len(owner_pool)]
        owner_index += 1
        return selected_owner

    for index, docs_folder in enumerate(doc_folders, start=1):
        folder_name = numbered_slug_title(docs_folder)
        folder_slug = slugify(folder_name)
        folder = session.scalars(select(Folder).where(Folder.slug == folder_slug)).one_or_none()
        if folder is None:
            folder = Folder(
                user_id=owner.id,
                name=folder_name,
                slug=folder_slug,
                path=folder_slug,
                sort_order=index * 10,
            )
            session.add(folder)
            session.flush()
            folder_count += 1
        else:
            folder.name = folder_name
            folder.user_id = owner.id
            folder.sort_order = index * 10

        for markdown_path in sorted(docs_folder.glob("*.md")):
            note_owner = next_note_owner()
            source_markdown = markdown_path.read_text(encoding="utf-8")
            title, body = markdown_title_and_body(
                source_markdown,
                numbered_slug_title(markdown_path),
            )
            existing_note = session.scalars(
                select(Note).where(Note.folder_id == folder.id, Note.title == title)
            ).one_or_none()
            note = existing_note or Note(
                id=new_id(),
                user_id=note_owner.id,
                folder_id=folder.id,
                title=title,
                source_type="markdown",
                note_path="",
            )
            if existing_note is None:
                session.add(note)

            paths = storage.note_paths(
                username=note_owner.username,
                folder=folder.path,
                filename=note.id,
                title=title,
                source_extension=".md",
            )
            storage.prepare_folder_directory(paths.directory)
            paths.note_path.write_text(
                render_markdown_note(title=title, text=body),
                encoding="utf-8",
            )
            if paths.source_path is not None:
                paths.source_path.parent.mkdir(parents=True, exist_ok=True)
                paths.source_path.write_text(source_markdown, encoding="utf-8")

            note.user_id = note_owner.id
            note.folder_id = folder.id
            note.title = title
            note.status = "ready"
            note.source_type = "markdown"
            note.summary = summarize_text(body)
            note.filename = f"{note_stem(title, note.id)}.md"
            note.note_path = str(paths.note_path)

            if paths.source_path is not None:
                source_file = next(iter(note.source_files), None)
                if source_file is None:
                    source_file = SourceFile(
                        note_id=note.id,
                        filename=str(paths.source_path.relative_to(paths.directory)),
                        file_path=str(paths.source_path),
                        original_filename=markdown_path.name,
                        content_type="text/markdown",
                    )
                    session.add(source_file)
                else:
                    source_file.filename = str(paths.source_path.relative_to(paths.directory))
                    source_file.file_path = str(paths.source_path)
                    source_file.original_filename = markdown_path.name
                    source_file.content_type = "text/markdown"
            note_count += 1
    return folder_count, note_count


def main() -> int:
    args = parse_args()
    if not args.users_only and not args.docs_dir.is_dir():
        print(f"Docs directory not found: {args.docs_dir}", file=sys.stderr)
        return 2
    if not args.avatars_dir.is_dir():
        print(f"Avatars directory not found: {args.avatars_dir}", file=sys.stderr)
        return 2

    if args.data_dir is not None:
        os.environ["MIANOTES_DATA_DIR"] = str(args.data_dir)
    if args.database_url:
        os.environ["MIANOTES_DATABASE_URL"] = args.database_url
    from mianotes_web_service.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    if args.reset:
        reset_storage(settings)

    from mianotes_web_service.db.init import create_database, create_system_database
    from mianotes_web_service.db.session import SessionLocal, SystemSessionLocal

    if args.users_only:
        create_system_database()
        session_factory = SystemSessionLocal
    else:
        create_database()
        session_factory = SessionLocal

    folder_count = 0
    note_count = 0
    with session_factory() as session:
        admin, demo_users = seed_users(
            session,
            admin_email=args.admin_email,
            admin_name=args.admin_name,
            password=args.password,
            avatars_dir=args.avatars_dir,
            count=args.demo_user_count,
            data_dir=settings.data_dir,
            preserve_existing_passwords=args.preserve_existing_passwords,
        )
        if not args.users_only:
            note_owners = [admin, *demo_users] if args.random_note_owners else [admin]
            folder_count, note_count = seed_docs(
                session,
                owner=admin,
                note_owners=note_owners,
                docs_dir=args.docs_dir,
                data_dir=settings.data_dir,
                note_owner_seed=args.note_owner_seed,
            )
        session.commit()

    if args.users_only:
        print(f"Seeded {len(demo_users)} demo users and admin {args.admin_email}.")
    else:
        print(
            f"Seeded {note_count} notes in {folder_count} docs folders, "
            f"{len(demo_users)} demo users, and admin {args.admin_email}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
