from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from gspread.exceptions import APIError

from app.services.google_sheets import GoogleSheetsSyncService
from app.schemas_google import GoogleSceneListResponse, GoogleSceneSummary, GoogleShotSummary

router = APIRouter(prefix="/google-sheets", tags=["google-sheets"])
_warm_cache_status = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "scenes": 0,
    "warmed": 0,
    "failed": 0,
    "error": None,
}


@router.get("/scene-list", response_model=GoogleSceneListResponse)
def read_scene_list(
    include_shots: bool = Query(default=False),
    refresh: bool = Query(default=False),
) -> GoogleSceneListResponse:
    service = GoogleSheetsSyncService()
    if not service.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets is not configured")
    try:
        return service.fetch_scene_list_with_shots(include_shots=include_shots, force_refresh=refresh)
    except APIError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", 502)
        if status_code == 429:
            raise HTTPException(status_code=429, detail="Google Sheets quota exceeded. Please retry shortly.") from exc
        raise HTTPException(status_code=502, detail="Google Sheets API request failed.") from exc


def _run_cache_warm(refresh: bool) -> None:
    _warm_cache_status.update(
        {
            "running": True,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "error": None,
        }
    )
    try:
        result = GoogleSheetsSyncService().warm_scene_cache(force_refresh=refresh)
        _warm_cache_status.update(result)
    except Exception as exc:
        _warm_cache_status["error"] = str(exc)
    finally:
        _warm_cache_status["running"] = False
        _warm_cache_status["finished_at"] = datetime.now().isoformat(timespec="seconds")


@router.post("/cache/warm")
def warm_google_sheets_cache(
    background_tasks: BackgroundTasks,
    refresh: bool = Query(default=False),
) -> dict:
    service = GoogleSheetsSyncService()
    if not service.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets is not configured")
    if not _warm_cache_status["running"]:
        background_tasks.add_task(_run_cache_warm, refresh)
    return _warm_cache_status


@router.get("/cache/warm")
def read_google_sheets_cache_status() -> dict:
    return _warm_cache_status


@router.get("/scene-list/{scene_code}/shots", response_model=GoogleSceneSummary)
def read_scene_shots(scene_code: str, refresh: bool = Query(default=False)) -> GoogleSceneSummary:
    service = GoogleSheetsSyncService()
    if not service.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets is not configured")

    try:
        scene = service.fetch_scene_shots(scene_code, force_refresh=refresh)
    except APIError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", 502)
        if status_code == 429:
            raise HTTPException(status_code=429, detail="Google Sheets quota exceeded. Please retry shortly.") from exc
        raise HTTPException(status_code=502, detail="Google Sheets API request failed.") from exc

    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.get("/scene-list/{scene_code}/shots/{shot_code}/detail", response_model=GoogleShotSummary)
def read_shot_detail(scene_code: str, shot_code: str) -> GoogleShotSummary:
    service = GoogleSheetsSyncService()
    if not service.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets is not configured")

    try:
        shot = service.fetch_shot_detail(scene_code, shot_code)
    except APIError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", 502)
        if status_code == 429:
            raise HTTPException(status_code=429, detail="Google Sheets quota exceeded. Please retry shortly.") from exc
        raise HTTPException(status_code=502, detail="Google Sheets API request failed.") from exc

    if shot is None:
        raise HTTPException(status_code=404, detail="Shot detail not found")
    return shot
