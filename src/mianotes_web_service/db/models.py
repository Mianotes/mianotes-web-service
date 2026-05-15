from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    topics: Mapped[list[Topic]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Topic.user_id",
    )
    notes: Mapped[list[Note]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_topics_user_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    user: Mapped[User] = relationship(back_populates="topics", foreign_keys=[user_id])
    notes: Mapped[list[Note]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class Note(Base, TimestampMixin):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ready", nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="text", nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    share_token_hash: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note_path: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="notes")
    topic: Mapped[Topic] = relationship(back_populates="notes")
    source_files: Mapped[list[SourceFile]] = relationship(
        back_populates="note",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list[Comment]] = relationship(
        back_populates="note",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary="note_tags",
        back_populates="notes",
    )


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    note_id: Mapped[str] = mapped_column(ForeignKey("notes.id"), index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    note: Mapped[Note] = relationship(back_populates="source_files")


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    note_id: Mapped[str] = mapped_column(ForeignKey("notes.id"), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str | None] = mapped_column(Text)
    comments_path: Mapped[str] = mapped_column(Text, default="", nullable=False)

    note: Mapped[Note] = relationship(back_populates="comments")
    user: Mapped[User | None] = relationship()


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

    note_id: Mapped[str] = mapped_column(
        ForeignKey("notes.id"),
        primary_key=True,
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class SessionToken(Base):
    __tablename__ = "session_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship()
