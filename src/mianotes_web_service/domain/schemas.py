from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl

MAX_TAGS_PER_NOTE = 5


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)


class UserRead(BaseModel):
    id: str
    email: EmailStr
    name: str
    username: str
    is_admin: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TopicCreate(BaseModel):
    user_id: str | None = None
    name: str = Field(min_length=1, max_length=200)


class TopicUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TopicRead(BaseModel):
    id: str
    user_id: str
    name: str
    slug: str
    archived_at: datetime | None = None
    archived_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteCreateFromText(BaseModel):
    user_id: str | None = None
    topic_id: str
    text: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_NOTE)


class NoteCreateFromUrl(BaseModel):
    topic_id: str
    url: HttpUrl
    title: str | None = Field(default=None, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_NOTE)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    text: str | None = Field(default=None, min_length=1)
    is_published: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS_PER_NOTE)


class TagRead(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TagsUpdate(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_NOTE)


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


class CommentUpdate(BaseModel):
    body: str = Field(min_length=1)


class CommentRead(BaseModel):
    id: str
    note_id: str
    user: UserRead | None = None
    body: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApiAction(BaseModel):
    method: str
    url: str


class NoteRead(BaseModel):
    id: str
    user: UserRead
    topic: TopicRead
    created_at: datetime
    updated_at: datetime
    title: str
    status: str
    source_type: str
    revision_number: int
    is_published: bool
    published_at: datetime | None = None
    shared_at: datetime | None = None
    text: str
    note_url: str
    source_files: list[dict[str, object]]
    comments_count: int
    comments_url: str
    tags: list[TagRead]
    share_url: str | None = None
    actions: dict[str, ApiAction]

    model_config = {"from_attributes": True}


class NoteListItem(BaseModel):
    id: str
    user_id: str
    topic_id: str
    title: str
    status: str
    source_type: str
    revision_number: int
    is_published: bool
    note_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    note: NoteListItem
    line_number: int
    column: int
    excerpt: str


class EmailCheck(BaseModel):
    email: EmailStr


class EmailCheckResult(BaseModel):
    user_id: str | None
    is_first_user: bool | None = None


class JoinRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1)
    password_confirmation: str | None = Field(default=None, min_length=1)


class LoginRequest(BaseModel):
    user_id: str
    password: str = Field(min_length=1)


class SessionRead(BaseModel):
    user: UserRead

    model_config = {"from_attributes": True}


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    user_id: str | None = None
    scopes: list[str] = Field(default_factory=lambda: ["notes:read"], min_length=1)
    expires_at: datetime | None = None


class ApiTokenRead(BaseModel):
    id: str
    user: UserRead
    name: str
    token_prefix: str
    scopes: list[str]
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


class ApiTokenCreated(ApiTokenRead):
    token: str


JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class MiaJobRead(BaseModel):
    id: str
    user: UserRead
    note_id: str | None = None
    job_type: str
    status: JobStatus
    input: dict[str, object]
    result: dict[str, object]
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class NoteIngestionRead(NoteRead):
    note_id: str
    job_id: str
    job_status: JobStatus
    note_api_url: str
    job_api_url: str
    job: MiaJobRead
