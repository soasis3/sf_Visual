from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models import AEStatus, RenderStatus, ShotStatus, TaskStatus


class ShotBase(BaseModel):
    project_code: str
    sequence_code: str | None = None
    shot_code: str
    scene_number: str | None = None
    cut_number: str | None = None
    title: str | None = None
    description: str | None = None
    frame_start: int | None = None
    frame_end: int | None = None
    fps: int | None = 24
    assignee: str | None = None
    due_date: date | None = None
    status: ShotStatus = ShotStatus.READY
    render_status: RenderStatus = RenderStatus.WAITING
    ae_status: AEStatus = AEStatus.NOT_STARTED
    source: str = "manual"


class ShotCreate(ShotBase):
    pass


class ShotUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    frame_start: int | None = None
    frame_end: int | None = None
    fps: int | None = None
    assignee: str | None = None
    due_date: date | None = None
    status: ShotStatus | None = None
    render_status: RenderStatus | None = None
    ae_status: AEStatus | None = None


class TaskBase(BaseModel):
    task_type: str
    status: TaskStatus = TaskStatus.NOT_STARTED
    assignee: str | None = None
    notes: str | None = None


class TaskCreate(TaskBase):
    shot_id: int


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    assignee: str | None = None
    notes: str | None = None


class VersionBase(BaseModel):
    shot_id: int
    task_id: int | None = None
    version_number: int = Field(default=1, ge=1)
    dcc_app: str
    file_path: str | None = None
    preview_path: str | None = None
    status: str | None = None
    comment: str | None = None
    created_by: str | None = None


class VersionCreate(VersionBase):
    pass


class StatusEventRead(BaseModel):
    id: int
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    actor: str | None = None
    message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskRead(TaskBase):
    id: int
    shot_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VersionRead(VersionBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ShotRead(ShotBase):
    id: int
    created_at: datetime
    updated_at: datetime
    tasks: list[TaskRead] = []
    versions: list[VersionRead] = []
    status_events: list[StatusEventRead] = []

    model_config = {"from_attributes": True}


class SyncResult(BaseModel):
    source: str
    created: int
    updated: int
    skipped: int
    detail: str | None = None
