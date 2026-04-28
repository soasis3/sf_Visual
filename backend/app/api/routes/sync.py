from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import SyncResult
from app.services.google_sheets import GoogleSheetsSyncService

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/google-sheets/shots", response_model=SyncResult)
def sync_google_shots(db: Session = Depends(get_db)) -> SyncResult:
    service = GoogleSheetsSyncService()
    if not service.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets is not configured")

    counters = service.sync_shotmaster(db)
    return SyncResult(
        source="google_sheets",
        created=counters.created,
        updated=counters.updated,
        skipped=counters.skipped,
        detail="ShotMaster sync completed",
    )
