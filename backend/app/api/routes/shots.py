from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ShotCreate, ShotRead, ShotUpdate, TaskCreate, TaskRead, TaskUpdate, VersionCreate, VersionRead
from app.services.shot_service import (
    create_shot,
    create_task,
    create_version,
    get_shot,
    get_task,
    list_shots,
    update_shot,
    update_task,
)

router = APIRouter(prefix="/shots", tags=["shots"])


@router.get("", response_model=list[ShotRead])
def read_shots(db: Session = Depends(get_db)) -> list[ShotRead]:
    return list_shots(db)


@router.post("", response_model=ShotRead, status_code=status.HTTP_201_CREATED)
def create_shot_endpoint(payload: ShotCreate, db: Session = Depends(get_db)) -> ShotRead:
    return create_shot(db, payload)


@router.get("/{shot_id}", response_model=ShotRead)
def read_shot(shot_id: int, db: Session = Depends(get_db)) -> ShotRead:
    shot = get_shot(db, shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    return shot


@router.patch("/{shot_id}", response_model=ShotRead)
def update_shot_endpoint(shot_id: int, payload: ShotUpdate, db: Session = Depends(get_db)) -> ShotRead:
    shot = get_shot(db, shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    return update_shot(db, shot, payload)


@router.post("/{shot_id}/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task_endpoint(shot_id: int, payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    if shot_id != payload.shot_id:
        raise HTTPException(status_code=400, detail="shot_id path and body mismatch")
    if get_shot(db, shot_id) is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    return create_task(db, payload)


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task_endpoint(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskRead:
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return update_task(db, task, payload)


@router.post("/{shot_id}/versions", response_model=VersionRead, status_code=status.HTTP_201_CREATED)
def create_version_endpoint(shot_id: int, payload: VersionCreate, db: Session = Depends(get_db)) -> VersionRead:
    if shot_id != payload.shot_id:
        raise HTTPException(status_code=400, detail="shot_id path and body mismatch")
    if get_shot(db, shot_id) is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    return create_version(db, payload)
