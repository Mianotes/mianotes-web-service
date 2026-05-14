from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


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


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    text: str | None = Field(default=None, min_length=1)


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
    text: str
    note_url: str
    source_files: list[dict[str, object]]
    comments_url: str
    actions: dict[str, ApiAction]

    model_config = {"from_attributes": True}


class NoteListItem(BaseModel):
    id: str
    user_id: str
    topic_id: str
    title: str
    status: str
    note_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmailCheck(BaseModel):
    email: EmailStr


class EmailCheckResult(BaseModel):
    user_id: str | None
    is_first_user: bool | None = None


class AdminSetup(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8)
    password_confirmation: str = Field(min_length=8)


class JoinRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1)


class LoginRequest(BaseModel):
    user_id: str
    password: str = Field(min_length=1)


class SessionRead(BaseModel):
    user: UserRead

    model_config = {"from_attributes": True}
