from pathlib import Path
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.preview_cache import find_cached_preview


router = APIRouter(prefix="/local-media", tags=["local-media"])
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}


def _media_type(path: Path) -> str:
    if path.suffix.lower() == ".mp4":
        return "video/mp4"
    if path.suffix.lower() == ".mov":
        return "video/quicktime"
    return "application/octet-stream"


@router.get("/ani/latest")
def read_latest_ani_video(
    scene_code: str = Query(...),
    shot_code: str = Query(...),
) -> FileResponse:
    latest = _find_latest_ani_video(scene_code, shot_code)
    return FileResponse(latest, media_type=_media_type(latest), filename=latest.name)


@router.get("/preview")
def read_cached_preview(
    scene_code: str = Query(...),
    shot_code: str = Query(...),
) -> FileResponse:
    preview = find_cached_preview(scene_code, shot_code)
    if preview is None:
        raise HTTPException(status_code=404, detail="Preview image not found")
    return FileResponse(preview)


@router.post("/ani/open")
def open_latest_ani_video(
    scene_code: str = Query(...),
    shot_code: str = Query(...),
) -> dict[str, str]:
    latest = _find_latest_ani_video(scene_code, shot_code)
    os.startfile(latest)
    return {"path": str(latest)}


def _find_latest_ani_video(scene_code: str, shot_code: str) -> Path:
    shot_folder = shot_code.split("_")[-1]
    ani_dir = get_settings().scene_root_path / scene_code / shot_folder / "ani"
    if not ani_dir.exists():
        raise HTTPException(status_code=404, detail="ANI folder not found")

    candidates = [
        path
        for path in ani_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]
    if not candidates:
        raise HTTPException(status_code=404, detail="ANI video not found")

    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return latest
