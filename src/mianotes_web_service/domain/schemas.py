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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TopicCreate(BaseModel):
    user_id: str
    name: str = Field(min_length=1, max_length=200)


class TopicUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TopicRead(BaseModel):
    id: str
    user_id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteCreateFromText(BaseModel):
    user_id: str
    topic_id: str
    text: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=300)


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
    note_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
