from pathlib import Path
import mimetypes
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.config import get_settings


PREVIEW_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def preview_cache_dir() -> Path:
    return get_settings().preview_cache_path


def find_cached_preview(scene_code: str, shot_code: str) -> Path | None:
    folder = preview_cache_dir() / _safe_name(scene_code)
    if not folder.exists():
        return None

    shot_key = _safe_name(shot_code)
    candidates = [
        path
        for path in folder.glob(f"{shot_key}.*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def cache_preview_image(scene_code: str | None, shot_code: str, image_url: str | None) -> Path | None:
    if not scene_code or not image_url:
        return None

    existing = find_cached_preview(scene_code, shot_code)
    if existing is not None:
        return existing

    try:
        request = Request(
            image_url,
            headers={"User-Agent": "SFVisualPreviewCache/1.0"},
        )
        with urlopen(request, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
            ext = _extension_for(image_url, content_type)
            if ext not in IMAGE_EXTENSIONS:
                return None
            data = response.read()
    except Exception:
        return None

    folder = preview_cache_dir() / _safe_name(scene_code)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_name(shot_code)}{ext}"
    try:
        path.write_bytes(data)
    except Exception:
        return None
    return path


def cache_preview_bytes(scene_code: str | None, shot_code: str, image_name: str, data: bytes) -> Path | None:
    if not scene_code or not data:
        return None

    existing = find_cached_preview(scene_code, shot_code)
    if existing is not None:
        return existing

    ext = Path(image_name).suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in IMAGE_EXTENSIONS:
        ext = ".png"

    folder = preview_cache_dir() / _safe_name(scene_code)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_name(shot_code)}{ext}"
    try:
        path.write_bytes(data)
    except Exception:
        return None
    return path


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value))


def _extension_for(url: str, content_type: str) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return ".jpg" if ext == ".jpeg" else ext

    guessed = mimetypes.guess_extension(content_type) or ""
    guessed = guessed.lower()
    if guessed == ".jpe":
        return ".jpg"
    if guessed == ".jpeg":
        return ".jpg"
    return guessed
