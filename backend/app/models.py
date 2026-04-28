from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ShotStatus(str, Enum):
    READY = "ready"
    WIP = "wip"
    REVIEW = "review"
    APPROVED = "approved"
    HOLD = "hold"
    DELIVERED = "delivered"


class TaskStatus(str, Enum):
    NOT_STARTED = "not_started"
    WIP = "wip"
    REVIEW = "review"
    APPROVED = "approved"
    HOLD = "hold"
    DONE = "done"


class RenderStatus(str, Enum):
    WAITING = "waiting"
    QUEUED = "queued"
    RENDERING = "rendering"
    COMPLETE = "complete"
    ERROR = "error"


class AEStatus(str, Enum):
    NOT_STARTED = "not_started"
    PREP = "prep"
    COMPING = "comping"
    REVIEW = "review"
    FINAL = "final"


class Shot(Base):
    __tablename__ = "shots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_code: Mapped[str] = mapped_column(String(32), index=True)
    sequence_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    shot_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scene_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cut_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ShotStatus] = mapped_column(SqlEnum(ShotStatus), default=ShotStatus.READY)
    render_status: Mapped[RenderStatus] = mapped_column(SqlEnum(RenderStatus), default=RenderStatus.WAITING)
    ae_status: Mapped[AEStatus] = mapped_column(SqlEnum(AEStatus), default=AEStatus.NOT_STARTED)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="shot", cascade="all, delete-orphan")
    versions: Mapped[list["Version"]] = relationship(back_populates="shot", cascade="all, delete-orphan")
    status_events: Mapped[list["StatusEvent"]] = relationship(back_populates="shot", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shot_id: Mapped[int] = mapped_column(ForeignKey("shots.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[TaskStatus] = mapped_column(SqlEnum(TaskStatus), default=TaskStatus.NOT_STARTED)
    assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shot: Mapped["Shot"] = relationship(back_populates="tasks")
    versions: Mapped[list["Version"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    status_events: Mapped[list["StatusEvent"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class Version(Base):
    __tablename__ = "versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shot_id: Mapped[int] = mapped_column(ForeignKey("shots.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    dcc_app: Mapped[str] = mapped_column(String(32))
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    shot: Mapped["Shot"] = relationship(back_populates="versions")
    task: Mapped["Task | None"] = relationship(back_populates="versions")


class StatusEvent(Base):
    __tablename__ = "status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shot_id: Mapped[int] = mapped_column(ForeignKey("shots.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    from_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    shot: Mapped["Shot"] = relationship(back_populates="status_events")
    task: Mapped["Task | None"] = relationship(back_populates="status_events")
