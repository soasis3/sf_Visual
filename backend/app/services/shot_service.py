from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Shot, StatusEvent, Task, Version
from app.schemas import ShotCreate, ShotUpdate, TaskCreate, TaskUpdate, VersionCreate


def list_shots(db: Session) -> list[Shot]:
    stmt = (
        select(Shot)
        .options(selectinload(Shot.tasks), selectinload(Shot.versions), selectinload(Shot.status_events))
        .order_by(Shot.project_code, Shot.sequence_code, Shot.shot_code)
    )
    return list(db.scalars(stmt).all())


def get_shot(db: Session, shot_id: int) -> Shot | None:
    stmt = (
        select(Shot)
        .where(Shot.id == shot_id)
        .options(selectinload(Shot.tasks), selectinload(Shot.versions), selectinload(Shot.status_events))
    )
    return db.scalars(stmt).first()


def get_shot_by_code(db: Session, shot_code: str) -> Shot | None:
    stmt = select(Shot).where(Shot.shot_code == shot_code)
    return db.scalars(stmt).first()


def create_shot(db: Session, payload: ShotCreate) -> Shot:
    shot = Shot(**payload.model_dump())
    db.add(shot)
    db.flush()
    db.add(
        StatusEvent(
            shot_id=shot.id,
            event_type="shot_created",
            to_status=shot.status.value,
            actor="system",
            message="Shot created",
        )
    )
    db.commit()
    db.refresh(shot)
    return shot


def update_shot(db: Session, shot: Shot, payload: ShotUpdate) -> Shot:
    before_status = shot.status.value
    before_render_status = shot.render_status.value
    before_ae_status = shot.ae_status.value

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(shot, key, value)

    db.add(shot)

    if shot.status.value != before_status:
        db.add(
            StatusEvent(
                shot_id=shot.id,
                event_type="shot_status_changed",
                from_status=before_status,
                to_status=shot.status.value,
                actor="api",
            )
        )

    if shot.render_status.value != before_render_status:
        db.add(
            StatusEvent(
                shot_id=shot.id,
                event_type="render_status_changed",
                from_status=before_render_status,
                to_status=shot.render_status.value,
                actor="api",
            )
        )

    if shot.ae_status.value != before_ae_status:
        db.add(
            StatusEvent(
                shot_id=shot.id,
                event_type="ae_status_changed",
                from_status=before_ae_status,
                to_status=shot.ae_status.value,
                actor="api",
            )
        )

    db.commit()
    db.refresh(shot)
    return shot


def create_task(db: Session, payload: TaskCreate) -> Task:
    task = Task(**payload.model_dump())
    db.add(task)
    db.flush()
    db.add(
        StatusEvent(
            shot_id=task.shot_id,
            task_id=task.id,
            event_type="task_created",
            to_status=task.status.value,
            actor="system",
            message=f"{task.task_type} task created",
        )
    )
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task: Task, payload: TaskUpdate) -> Task:
    before_status = task.status.value
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)

    db.add(task)

    if task.status.value != before_status:
        db.add(
            StatusEvent(
                shot_id=task.shot_id,
                task_id=task.id,
                event_type="task_status_changed",
                from_status=before_status,
                to_status=task.status.value,
                actor="api",
            )
        )

    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> Task | None:
    return db.get(Task, task_id)


def create_version(db: Session, payload: VersionCreate) -> Version:
    version = Version(**payload.model_dump())
    db.add(version)
    db.flush()
    db.add(
        StatusEvent(
            shot_id=version.shot_id,
            task_id=version.task_id,
            event_type="version_created",
            actor=version.created_by or "api",
            message=f"{version.dcc_app} v{version.version_number:03d}",
        )
    )
    db.commit()
    db.refresh(version)
    return version
