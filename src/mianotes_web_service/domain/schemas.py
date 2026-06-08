from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl

MAX_TAGS_PER_NOTE = 5


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=64)
    role: str | None = Field(default=None, max_length=120)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=64)
    role: str | None = Field(default=None, max_length=120)


class UserAdminUpdate(BaseModel):
    is_admin: bool


class UserPasswordUpdate(BaseModel):
    password: str = Field(min_length=1)
    password_confirmation: str = Field(min_length=1)


class UserRead(BaseModel):
    id: str
    email: EmailStr
    name: str
    username: str
    phone: str | None = None
    role: str | None = None
    photo_url: str | None = None
    is_admin: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FolderCreate(BaseModel):
    user_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    is_pinned: bool = False


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_pinned: bool | None = None


class FolderReorder(BaseModel):
    folder_ids: list[str] = Field(min_length=1)


class FolderRestore(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_pinned: bool | None = None


class FolderRead(BaseModel):
    id: str
    user_id: str
    name: str
    slug: str
    path: str
    is_pinned: bool
    sort_order: int
    archived_at: datetime | None = None
    archived_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteCreateFromText(BaseModel):
    user_id: str | None = None
    folder_id: str
    text: str = ""
    title: str | None = Field(default=None, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_NOTE)


class NoteCreateFromUrl(BaseModel):
    folder_id: str
    url: HttpUrl
    title: str | None = Field(default=None, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_NOTE)


class NoteUpdate(BaseModel):
    folder_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    text: str | None = Field(default=None, min_length=1)
    is_published: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS_PER_NOTE)


class NoteStarUpdate(BaseModel):
    is_starred: bool


class TagRead(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserProfileSummaryRead(BaseModel):
    user_id: str
    notes_count: int = 0
    tags_count: int = 0
    folders_count: int = 0
    tags: list[TagRead] = Field(default_factory=list)


class TagsUpdate(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_NOTE)


class MiaPromptCreate(BaseModel):
    prompt: str
    markdown: str | None = None


class MiaPromptRead(BaseModel):
    type: Literal["prompt"] = "prompt"
    prompt: str
    note_id: str
    text: str
    format: Literal["markdown"] = "markdown"


class ApiAction(BaseModel):
    method: str
    url: str


class NoteRead(BaseModel):
    id: str
    user: UserRead
    folder_id: str
    folder: FolderRead
    created_at: datetime
    updated_at: datetime
    title: str
    status: str
    source_type: str
    revision_number: int
    is_published: bool
    is_starred: bool
    published_at: datetime | None = None
    summary: str
    shared_at: datetime | None = None
    text: str
    note_url: str
    source_files: list[dict[str, object]]
    tags: list[TagRead]
    share_url: str | None = None
    job_id: str | None = None
    job_status: str | None = None
    actions: dict[str, ApiAction]

    model_config = {"from_attributes": True}


class NoteListItem(BaseModel):
    id: str
    user_id: str
    folder_id: str
    title: str
    status: str
    source_type: str
    revision_number: int
    is_published: bool
    is_starred: bool
    summary: str = ""
    filename: str | None = None
    note_path: str
    source_files: list[dict[str, object]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    tags: list[TagRead] = Field(default_factory=list)
    job_id: str | None = None
    job_status: str | None = None

    model_config = {"from_attributes": True}


class NoteListCounts(BaseModel):
    folders: dict[str, int] = Field(default_factory=dict)


class NoteListPage(BaseModel):
    items: list[NoteListItem]
    total: int | None = None
    limit: int
    next_cursor: str | None = None
    counts: NoteListCounts | None = None


class FolderNoteCounts(BaseModel):
    folders: dict[str, int] = Field(default_factory=dict)


class SearchResult(BaseModel):
    note: NoteListItem
    line_number: int
    column: int
    excerpt: str


class ContextResult(BaseModel):
    note: NoteListItem
    text: str
    matched_by: Literal["title", "search"]
    line_number: int | None = None
    excerpt: str | None = None


class ContextResponse(BaseModel):
    folder: str
    title: str
    limit: int
    total: int
    results: list[ContextResult]


class EmailCheck(BaseModel):
    email: EmailStr


class EmailCheckResult(BaseModel):
    user_id: str | None
    is_first_user: bool | None = None
    master_password_owner_name: str | None = None
    signup_disabled: bool = False


class JoinRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1)
    password_confirmation: str | None = Field(default=None, min_length=1)
    workspace_access_mode: str | None = None


class LoginRequest(BaseModel):
    user_id: str
    password: str = Field(min_length=1)


class SessionRead(BaseModel):
    user: UserRead

    model_config = {"from_attributes": True}


class StorageCapacityRead(BaseModel):
    data_dir: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    data_size_bytes: int
    used_percent: float
    cache_seconds: int
    refreshed_at: datetime
    cache_expires_at: datetime


class StorageLocationRead(BaseModel):
    id: str
    name: str
    folder_path: str
    database_path: str
    is_active: bool
    database_exists: bool
    notes_count: int | None = None
    users_count: int | None = None
    last_updated_at: datetime | None = None


class StorageLocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    folder_path: str = Field(min_length=1, max_length=1000)
    import_existing_markdown: bool | None = None


class StorageSettingsRead(BaseModel):
    active_location: str
    data_dir: str
    database_path: str
    locations: list[StorageLocationRead]


class StorageSwitchRequest(BaseModel):
    location_id: str = Field(min_length=1)


class StorageSwitchRead(BaseModel):
    storage: StorageSettingsRead
    session_ended: bool = False


class ServiceApiKeyRead(BaseModel):
    token: str
    api_url: str


class AiProviderSettingsRead(BaseModel):
    provider: str
    model: str | None = None
    base_url: str | None = None
    has_api_key: bool = False


class AiProviderSettingsUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    model: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)


class AiProviderConnect(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    model: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)


class AiProviderConnectRead(AiProviderSettingsRead):
    connected: bool = True
    message: str


class SkillInstallCreate(BaseModel):
    api_url: str = Field(min_length=1, max_length=500)


class SkillInstallRead(BaseModel):
    install_url: str
    command: str
    expires_at: datetime


class AgentSessionRead(BaseModel):
    token: str
    token_type: str = "bearer"
    client_key: str
    client: str
    expires_at: datetime
    user: UserRead
    scopes: list[str]


class ShareSettingsRead(BaseModel):
    workspace_url: str | None = None


class ShareSettingsUpdate(BaseModel):
    workspace_url: str | None = Field(default=None, max_length=500)


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


class MiaJobLogEntry(BaseModel):
    timestamp: datetime
    status: str
    command: str
    response: str | None = None


class AgentClientRead(BaseModel):
    key: str
    name: str


class MiaJobRead(BaseModel):
    id: str
    user: UserRead
    client: AgentClientRead | None = None
    note_id: str | None = None
    note_title: str | None = None
    job_type: str
    status: JobStatus
    input: dict[str, object]
    result: dict[str, object]
    log: list[MiaJobLogEntry] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class MiaJobListItem(BaseModel):
    id: str
    user: UserRead
    client: AgentClientRead | None = None
    note_id: str | None = None
    note_title: str | None = None
    job_type: str
    status: JobStatus
    input: dict[str, object] | None = None
    result: dict[str, object] | None = None
    log: list[MiaJobLogEntry] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class MiaJobListPage(BaseModel):
    items: list[MiaJobListItem]
    limit: int
    next_cursor: str | None = None


class NoteIngestionRead(NoteRead):
    note_id: str
    job_id: str
    job_status: JobStatus
    note_api_url: str
    job_api_url: str
    job: MiaJobRead


class PublishThemeRead(BaseModel):
    id: str
    name: str
    description: str
    version: str


class PublishDraftRead(BaseModel):
    theme: str
    folder_id: str | None = None
    tag_id: str | None = None
    site_configuration: dict[str, object]
    navigation: list[dict[str, object]]
    updated_notes: list[dict[str, object]]
    generated_at: datetime


class PublishRequest(BaseModel):
    folder_id: str | None = None
    tag_id: str | None = None
    theme: str = Field(default="mialight", min_length=1, max_length=80)
    site_configuration: dict[str, object]
    navigation: list[dict[str, object]]
    updated_notes: list[dict[str, object]]


class PublishRead(BaseModel):
    id: str
    theme: str
    version: str
    folder_id: str | None = None
    tag_id: str | None = None
    note_count: int
    html_path: str
    markdown_path: str
    url_path: str
    site_url: str
    download_url: str
    created_at: datetime
