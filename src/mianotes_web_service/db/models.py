from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str | None] = mapped_column(String(120))
    avatar_path: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    folders: Mapped[list[Folder]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Folder.user_id",
    )
    notes: Mapped[list[Note]] = relationship(back_populates="user", cascade="all, delete-orphan")
    note_stars: Mapped[list[NoteStar]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    api_tokens: Mapped[list[ApiToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list[MiaJob]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def photo_url(self) -> str | None:
        if not self.avatar_path:
            return None
        return f"/{self.avatar_path}"


class Folder(Base, TimestampMixin):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_folders_slug"),
        Index("ix_folders_path", "path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    user: Mapped[User] = relationship(back_populates="folders", foreign_keys=[user_id])
    notes: Mapped[list[Note]] = relationship(back_populates="folder", cascade="all, delete-orphan")


class Note(Base, TimestampMixin):
    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_created_id", "created_at", "id"),
        Index("ix_notes_folder_created_id", "folder_id", "created_at", "id"),
        Index("ix_notes_user_created_id", "user_id", "created_at", "id"),
        Index(
            "ix_notes_folder_published_filename",
            "folder_id",
            "is_published",
            "filename",
        ),
        Index("ix_notes_folder_filename", "folder_id", "filename"),
        Index("ix_notes_published_filename", "is_published", "filename"),
        Index("ix_notes_folder_title", "folder_id", "title"),
        Index("ix_notes_folder_updated_at", "folder_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    folder_id: Mapped[str] = mapped_column(ForeignKey("folders.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ready", nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="text", nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    share_token_hash: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filename: Mapped[str | None] = mapped_column(String(500))
    note_path: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="notes")
    folder: Mapped[Folder] = relationship(back_populates="notes")
    source_files: Mapped[list[SourceFile]] = relationship(
        back_populates="note",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary="note_tags",
        back_populates="notes",
    )
    stars: Mapped[list[NoteStar]] = relationship(
        back_populates="note",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list[MiaJob]] = relationship(back_populates="note", cascade="all, delete-orphan")


class PublishedSite(Base, TimestampMixin):
    __tablename__ = "published_sites"
    __table_args__ = (
        Index("ix_published_sites_scope_created_id", "folder_id", "tag_id", "created_at", "id"),
        Index("ix_published_sites_created_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id"), index=True)
    tag_id: Mapped[str | None] = mapped_column(ForeignKey("tags.id"), index=True)
    theme: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    html_path: Mapped[str] = mapped_column(Text, nullable=False)
    markdown_path: Mapped[str] = mapped_column(Text, nullable=False)
    url_path: Mapped[str] = mapped_column(Text, nullable=False)
    site_configuration: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    navigation: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    note_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship()
    folder: Mapped[Folder | None] = relationship()
    tag: Mapped[Tag | None] = relationship()


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (Index("ix_source_files_note_filename", "note_id", "filename"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    note_id: Mapped[str] = mapped_column(ForeignKey("notes.id"), index=True, nullable=False)
    filename: Mapped[str | None] = mapped_column(String(700))
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    note: Mapped[Note] = relationship(back_populates="source_files")


class Tag(Base, TimestampMixin):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)

    notes: Mapped[list[Note]] = relationship(
        secondary="note_tags",
        back_populates="tags",
    )


class NoteTag(Base):
    __tablename__ = "note_tags"
    __table_args__ = (Index("ix_note_tags_tag_note", "tag_id", "note_id"),)

    note_id: Mapped[str] = mapped_column(
        ForeignKey("notes.id"),
        primary_key=True,
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NoteStar(Base):
    __tablename__ = "note_stars"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        primary_key=True,
    )
    note_id: Mapped[str] = mapped_column(
        ForeignKey("notes.id"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="note_stars")
    note: Mapped[Note] = relationship(back_populates="stars")


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class SessionToken(Base):
    __tablename__ = "session_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship()


class ApiToken(Base, TimestampMixin):
    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="api_tokens")


class SkillInstallCode(Base, TimestampMixin):
    __tablename__ = "skill_install_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    api_url: Mapped[str] = mapped_column(String(500), nullable=False)
    client_name: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped[User] = relationship()


class MiaJob(Base, TimestampMixin):
    __tablename__ = "mia_jobs"
    __table_args__ = (
        Index("ix_mia_jobs_status_finished_created", "status", "finished_at", "created_at", "id"),
        Index("ix_mia_jobs_user_status_created", "user_id", "status", "created_at", "id"),
        Index("ix_mia_jobs_note_status_created", "note_id", "status", "created_at", "id"),
        Index("ix_mia_jobs_note_created_id", "note_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    note_id: Mapped[str | None] = mapped_column(ForeignKey("notes.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), index=True, default="queued", nullable=False)
    input_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    log_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    client_key: Mapped[str | None] = mapped_column(String(80))
    client_name: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="jobs")
    note: Mapped[Note | None] = relationship(back_populates="jobs")
