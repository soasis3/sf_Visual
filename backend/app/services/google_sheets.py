from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
import posixpath
import re
import zipfile
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
import time
import xml.etree.ElementTree as ET

import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from gspread.utils import ValueRenderOption
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AEStatus, RenderStatus, ShotStatus
from app.schemas_google import (
    GoogleSceneListResponse,
    GoogleSceneSummary,
    GoogleShotLevel,
    GoogleShotSummary,
    GoogleShotTaskStatus,
)
from app.schemas import ShotCreate
from app.services.preview_cache import cache_preview_bytes, cache_preview_image, find_cached_preview
from app.services.shot_service import get_shot_by_code


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

SCENE_LIST_CACHE_TTL_SECONDS = 300
SCENE_SHOTS_CACHE_TTL_SECONDS = 300
DISK_CACHE_TTL_SECONDS = 60 * 60 * 24
DISK_CACHE_SCHEMA_VERSION = "v14"
STAFF_DAYS_PER_LEVEL_SCORE = 0.32
LEAD_DAYS_PER_LEVEL_SCORE = 0.23
_scene_list_cache: dict[str, tuple[float, GoogleSceneListResponse]] = {}
_scene_shots_cache: dict[str, tuple[float, GoogleSceneSummary]] = {}
OMIT_KEYWORDS = ("omit", "omitted", "오밋", "제외")


@dataclass
class SyncCounters:
    created: int = 0
    updated: int = 0
    skipped: int = 0


class GoogleSheetsSyncService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(
            self.settings.google_service_account_file and self.settings.google_sheets_spreadsheet_id
        )

    def _get_client(self) -> gspread.Client:
        credentials = self._get_credentials()
        return gspread.authorize(credentials)

    def _get_credentials(self) -> Credentials:
        return Credentials.from_service_account_file(
            self.settings.google_service_account_file,
            scopes=SCOPES,
        )

    def fetch_shotmaster_rows(self) -> list[dict]:
        if not self.is_configured():
            raise RuntimeError("Google Sheets integration is not configured.")

        client = self._get_client()
        spreadsheet = client.open_by_key(self.settings.google_sheets_spreadsheet_id)
        worksheet = spreadsheet.worksheet(self.settings.google_shotmaster_worksheet)
        return worksheet.get_all_records()

    def fetch_scene_list_with_shots(
        self,
        include_shots: bool = False,
        target_scene_code: str | None = None,
        force_refresh: bool = False,
    ) -> GoogleSceneListResponse:
        cache_key = f"{include_shots}:{target_scene_code or '*'}"
        cached = _scene_list_cache.get(cache_key)
        if not force_refresh and cached and time.time() - cached[0] < SCENE_LIST_CACHE_TTL_SECONDS:
            return cached[1]

        disk_key = self._scene_list_cache_key(include_shots, target_scene_code)
        if not force_refresh:
            disk_cached = self._read_disk_cache(disk_key, GoogleSceneListResponse)
            if disk_cached is not None:
                _scene_list_cache[cache_key] = (time.time(), disk_cached)
                return disk_cached

        if not self.is_configured():
            raise RuntimeError("Google Sheets integration is not configured.")

        client = self._get_client()
        spreadsheet = client.open_by_key(self.settings.google_sheets_spreadsheet_id)
        worksheet = spreadsheet.worksheet(self.settings.google_scene_list_worksheet)
        rows = worksheet.get_all_values()
        if len(rows) < 4:
            return GoogleSceneListResponse(
                spreadsheet_title=spreadsheet.title,
                worksheet_title=worksheet.title,
                scenes=[],
            )

        data_rows = rows[3:]
        scenes: list[GoogleSceneSummary] = []
        compositing_progress_col = self._find_header_column(rows[:3], "COM")

        for row in data_rows:
            if self._is_omit_row(row):
                continue

            shotlist_url = self._find_shotlist_url(row)
            if not shotlist_url:
                continue

            scene_code = self._string_or_none(self._get_by_index(row, 25))
            normalized_scene_code = self._normalize_scene_code(scene_code)
            spreadsheet_id = self._extract_spreadsheet_id(shotlist_url)
            if not spreadsheet_id:
                continue

            if target_scene_code and normalized_scene_code != self._normalize_scene_code(target_scene_code):
                continue

            shots: list[GoogleShotSummary] = []
            if include_shots:
                shots = self._fetch_shots_from_scene_sheet(client, spreadsheet_id, normalized_scene_code)

            scene_summary = GoogleSceneSummary(
                scene_code=normalized_scene_code or self._derive_scene_code_from_name(self._get_by_index(row, 1)),
                scene_label=self._string_or_none(self._get_by_index(row, 0)),
                shotlist_name=self._string_or_none(self._get_by_index(row, 1)),
                shotlist_url=shotlist_url,
                shotlist_spreadsheet_id=spreadsheet_id,
                compositing_progress=self._parse_percent(self._get_by_index(row, compositing_progress_col)),
                total_shots=self._int_or_none(self._get_by_index(row, 2)),
                total_minutes=self._float_or_none(self._get_by_index(row, 3)),
                total_seconds=self._float_or_none(self._get_by_index(row, 4)),
                total_frames=self._int_or_none(self._normalize_int_string(self._get_by_index(row, 5))),
                shots=shots,
            )

            if self._is_omit_scene(scene_summary):
                continue

            scenes.append(scene_summary)

        response = GoogleSceneListResponse(
            spreadsheet_title=spreadsheet.title,
            worksheet_title=worksheet.title,
            scenes=scenes,
        )
        _scene_list_cache[cache_key] = (time.time(), response)
        self._write_disk_cache(disk_key, response)
        return response

    def fetch_scene_shots(self, scene_code: str, force_refresh: bool = False) -> GoogleSceneSummary | None:
        cached = _scene_shots_cache.get(scene_code)
        if not force_refresh and cached and time.time() - cached[0] < SCENE_SHOTS_CACHE_TTL_SECONDS:
            return cached[1]

        disk_key = self._scene_shots_cache_key(scene_code)
        if not force_refresh:
            disk_cached = self._read_disk_cache(disk_key, GoogleSceneSummary)
            if disk_cached is not None:
                _scene_shots_cache[scene_code] = (time.time(), disk_cached)
                return disk_cached

        response = self.fetch_scene_list_with_shots(
            include_shots=True,
            target_scene_code=scene_code,
            force_refresh=force_refresh,
        )
        if not response.scenes:
            return None
        scene = response.scenes[0]
        _scene_shots_cache[scene_code] = (time.time(), scene)
        self._write_disk_cache(disk_key, scene)
        return scene

    def fetch_shot_detail(self, scene_code: str, shot_code: str) -> GoogleShotSummary | None:
        response = self.fetch_scene_list_with_shots(force_refresh=False)
        normalized_scene_code = self._normalize_scene_code(scene_code)
        scene = next(
            (item for item in response.scenes if self._normalize_scene_code(item.scene_code) == normalized_scene_code),
            None,
        )
        if scene is None:
            return None

        client = self._get_client()
        spreadsheet = client.open_by_key(scene.shotlist_spreadsheet_id)
        target_shot_code = self._normalize_shot_code(normalized_scene_code, shot_code)

        for worksheet in self._detail_worksheets(spreadsheet, normalized_scene_code):
            rows = worksheet.get_all_values()
            if len(rows) < 4:
                continue

            columns = self._find_shot_detail_columns(rows[:3])
            for row in rows[3:]:
                shot_value = self._string_or_none(self._get_by_index(row, 0))
                if not shot_value:
                    continue
                normalized_shot_code = self._normalize_shot_code(normalized_scene_code, shot_value)
                if normalized_shot_code != target_shot_code:
                    continue

                return GoogleShotSummary(
                    shot_code=normalized_shot_code,
                    duration_frames=self._int_or_none(self._normalize_int_string(self._get_by_index(row, 2))),
                    preview_image_url=self._extract_image_url(self._get_by_index(row, 1)),
                    cam=self._string_or_none(self._get_by_index(row, 3)),
                    shot_description=self._string_or_none(self._get_by_index(row, columns.get("shot_description"))),
                    direction_lighting=self._string_or_none(self._get_by_index(row, columns.get("direction_note"))),
                    retake_note=self._string_or_none(self._get_by_index(row, columns.get("retake_note"))),
                    visual_statuses=[],
                    shot_level=None,
                    source_sheet_title=spreadsheet.title,
                    source_worksheet_title=worksheet.title,
                )

        return None

    def ensure_shot_preview_cached(self, scene_code: str, shot_code: str) -> Path | None:
        normalized_scene_code = self._normalize_scene_code(scene_code)
        normalized_shot_code = self._normalize_shot_code(normalized_scene_code, shot_code)

        cached = find_cached_preview(normalized_scene_code, normalized_shot_code)
        if cached is not None:
            return cached

        scene = self.fetch_scene_shots(normalized_scene_code, force_refresh=False)
        if scene is None or not scene.shotlist_spreadsheet_id:
            return None

        scene_shot = next(
            (
                shot
                for shot in (scene.shots or [])
                if self._normalize_shot_code(normalized_scene_code, shot.shot_code) == normalized_shot_code
            ),
            None,
        )
        if scene_shot and scene_shot.preview_image_url:
            cached = cache_preview_image(
                normalized_scene_code,
                normalized_shot_code,
                scene_shot.preview_image_url,
            )
            if cached is not None:
                return cached

        client = self._get_client()
        spreadsheet = client.open_by_key(scene.shotlist_spreadsheet_id)

        for worksheet in self._detail_worksheets(spreadsheet, normalized_scene_code):
            cached = self._cache_scene_preview_sheet(
                spreadsheet.id,
                worksheet,
                normalized_scene_code,
                target_shot_code=normalized_shot_code,
            )
            if cached is not None:
                return cached

        return find_cached_preview(normalized_scene_code, normalized_shot_code)

    def warm_scene_cache(self, force_refresh: bool = False) -> dict[str, int]:
        response = self.fetch_scene_list_with_shots(force_refresh=force_refresh)
        warmed = 0
        failed = 0

        for scene in response.scenes:
            if not scene.scene_code:
                continue
            try:
                if self.fetch_scene_shots(scene.scene_code, force_refresh=force_refresh) is not None:
                    warmed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        return {"scenes": len(response.scenes), "warmed": warmed, "failed": failed}

    def sync_shotmaster(self, db: Session) -> SyncCounters:
        counters = SyncCounters()
        rows = self.fetch_shotmaster_rows()

        for row in rows:
            normalized = self._normalize_shotmaster_row(row)
            if normalized is None:
                counters.skipped += 1
                continue

            existing = get_shot_by_code(db, normalized.shot_code)
            if existing is None:
                from app.services.shot_service import create_shot

                create_shot(db, normalized)
                counters.created += 1
                continue

            changed = False
            payload = normalized.model_dump()
            for key, value in payload.items():
                if getattr(existing, key) != value:
                    setattr(existing, key, value)
                    changed = True

            if changed:
                existing.source = "google_sheets"
                db.add(existing)
                counters.updated += 1
            else:
                counters.skipped += 1

        db.commit()
        return counters

    @staticmethod
    def _scene_list_cache_key(include_shots: bool, target_scene_code: str | None) -> str:
        shot_part = "with_shots" if include_shots else "scenes_only"
        scene_part = target_scene_code or "all"
        return f"scene_list_{shot_part}_{scene_part}"

    @staticmethod
    def _scene_shots_cache_key(scene_code: str) -> str:
        return f"scene_shots_{scene_code}"

    @staticmethod
    def _cache_dir() -> Path:
        return get_settings().google_sheets_cache_path

    def _cache_file(self, key: str) -> Path:
        safe_key = re.sub(r"[^a-zA-Z0-9_.-]+", "_", f"{DISK_CACHE_SCHEMA_VERSION}_{key}")
        return self._cache_dir() / f"{safe_key}.json"

    def _read_disk_cache(self, key: str, model_cls):
        path = self._cache_file(key)
        if not path.exists():
            return None
        try:
            if time.time() - path.stat().st_mtime > DISK_CACHE_TTL_SECONDS:
                return None
            return model_cls.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_disk_cache(self, key: str, model) -> None:
        cache_dir = self._cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file(key).write_text(model.model_dump_json(indent=2), encoding="utf-8")

    def _normalize_shotmaster_row(self, row: dict) -> ShotCreate | None:
        project_code = self._pick(row, "project_code", "project", "Project")
        shot_code = self._pick(row, "shot_code", "shot", "Shot", "cut_code")

        if not project_code or not shot_code:
            return None

        due_date_raw = self._pick(row, "due_date", "DueDate", "deadline")
        due_date = None
        if due_date_raw:
            try:
                due_date = datetime.fromisoformat(str(due_date_raw)).date()
            except ValueError:
                due_date = None

        return ShotCreate(
            project_code=str(project_code).strip(),
            sequence_code=self._string_or_none(self._pick(row, "sequence_code", "sequence", "Sequence")),
            shot_code=str(shot_code).strip(),
            scene_number=self._string_or_none(self._pick(row, "scene_number", "scene", "Scene")),
            cut_number=self._string_or_none(self._pick(row, "cut_number", "cut", "Cut")),
            title=self._string_or_none(self._pick(row, "title", "shot_title", "Title")),
            description=self._string_or_none(self._pick(row, "description", "notes", "Description")),
            frame_start=self._int_or_none(self._pick(row, "frame_start", "start_frame", "StartFrame")),
            frame_end=self._int_or_none(self._pick(row, "frame_end", "end_frame", "EndFrame")),
            fps=self._int_or_none(self._pick(row, "fps", "FPS")) or 24,
            assignee=self._string_or_none(self._pick(row, "assignee", "artist", "Assignee")),
            due_date=due_date,
            status=self._parse_enum(ShotStatus, self._pick(row, "status", "shot_status"), ShotStatus.READY),
            render_status=self._parse_enum(
                RenderStatus, self._pick(row, "render_status", "render"), RenderStatus.WAITING
            ),
            ae_status=self._parse_enum(AEStatus, self._pick(row, "ae_status", "after_effects"), AEStatus.NOT_STARTED),
            source="google_sheets",
        )

    @staticmethod
    def _pick(row: dict, *keys: str):
        for key in keys:
            if key in row and row[key] not in (None, ""):
                return row[key]
        return fallback_path

    @staticmethod
    def _string_or_none(value):
        if value in (None, ""):
            return None
        return str(value).strip()

    @staticmethod
    def _int_or_none(value):
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float_or_none(value):
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_enum(enum_cls, value, default):
        if value in (None, ""):
            return default

        normalized = str(value).strip().lower().replace(" ", "_")
        for member in enum_cls:
            if member.value == normalized:
                return member
        return default

    @staticmethod
    def _get_by_index(row: list, index: int):
        if index is None:
            return None
        if index < len(row):
            return row[index]
        return None

    @staticmethod
    def _normalize_int_string(value):
        if value in (None, ""):
            return None
        return str(value).replace(",", "")

    @staticmethod
    def _extract_spreadsheet_id(url: str | None) -> str | None:
        if not url:
            return None
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _derive_scene_code_from_name(name: str | None) -> str:
        if not name:
            return ""
        match = re.search(r"(\d{4})", str(name))
        return match.group(1) if match else str(name)

    @staticmethod
    def _find_shotlist_url(row: list[str]) -> str | None:
        for cell in row:
            value = str(cell).strip()
            if "/spreadsheets/d/" in value:
                return value
        return None

    @staticmethod
    def _find_header_column(rows: list[list[str]], header_name: str) -> int | None:
        target = header_name.strip().lower()
        for row in rows:
            for index, cell in enumerate(row):
                if str(cell).strip().lower() == target:
                    return index
        return None

    @staticmethod
    def _parse_percent(value: str | int | float | None) -> float | None:
        if value in (None, ""):
            return None
        text = str(value).strip().replace("%", "").replace(",", "")
        try:
            number = float(text)
        except ValueError:
            return None
        return number * 100 if 0 < number <= 1 else number

    def _fetch_shots_from_scene_sheet(
        self,
        client: gspread.Client,
        spreadsheet_id: str,
        scene_code: str | None,
    ) -> list[GoogleShotSummary]:
        spreadsheet = client.open_by_key(spreadsheet_id)
        direction_worksheet = self._get_direction_worksheet(spreadsheet, scene_code)
        direction_display_rows = direction_worksheet.get_all_values() if direction_worksheet is not None else []
        direction_previews = {}
        if self.settings.cache_sheet_previews:
            direction_previews = self._extract_embedded_previews_by_shot_code(
                spreadsheet.id,
                direction_worksheet.id if direction_worksheet is not None else None,
                direction_worksheet.title if direction_worksheet is not None else "",
                scene_code,
                direction_display_rows,
            )
        ani_task_statuses = self._extract_ani_task_statuses(spreadsheet, scene_code)

        visual_worksheet = self._get_scene_worksheet(spreadsheet, scene_code, "Vis_Review Note")
        if visual_worksheet is not None:
            shots = self._fetch_shots_from_visual_review(
                spreadsheet,
                visual_worksheet,
                scene_code,
                direction_previews,
                ani_task_statuses,
            )
            if shots:
                return shots

        worksheet = direction_worksheet or spreadsheet.get_worksheet(0)

        display_rows = direction_display_rows or worksheet.get_all_values()
        formula_rows = worksheet.get("A1:C400", value_render_option=ValueRenderOption.formula)
        embedded_previews = {}
        if self.settings.cache_sheet_previews:
            embedded_previews = self._extract_embedded_previews_from_xlsx(
                spreadsheet.id,
                worksheet.id,
                worksheet.title,
                scene_code,
                display_rows,
            )

        if len(display_rows) < 5:
            return []

        shots: list[GoogleShotSummary] = []
        for row_index in range(4, len(display_rows)):
            row = display_rows[row_index]
            shot_value = self._string_or_none(self._get_by_index(row, 0))
            if not shot_value or shot_value.endswith("_0000") or self._contains_omit(shot_value):
                continue
            if not self._has_meaningful_shot_row(row, detail_start_col=2):
                continue

            duration_value = self._get_by_index(row, 2)
            formula_row = formula_rows[row_index] if row_index < len(formula_rows) else []
            preview_formula = self._get_by_index(formula_row, 1)

            preview_image_url = self._extract_image_url(preview_formula, self._get_by_index(row, 1))
            normalized_shot_code = self._normalize_shot_code(scene_code, shot_value)
            if self.settings.cache_sheet_previews:
                cache_preview_image(scene_code, normalized_shot_code, preview_image_url)
                if not preview_image_url and normalized_shot_code in direction_previews:
                    image_name, image_data = direction_previews[normalized_shot_code]
                    cache_preview_bytes(scene_code, normalized_shot_code, image_name, image_data)
                elif not preview_image_url and row_index in embedded_previews:
                    image_name, image_data = embedded_previews[row_index]
                    cache_preview_bytes(scene_code, normalized_shot_code, image_name, image_data)

            visual_statuses = []
            visual_statuses.extend(ani_task_statuses.get(normalized_shot_code, []))

            shot_summary = GoogleShotSummary(
                shot_code=normalized_shot_code,
                duration_frames=self._int_or_none(self._normalize_int_string(duration_value)),
                preview_image_url=preview_image_url,
                cam=None,
                visual_statuses=visual_statuses,
                shot_level=self._calculate_shot_level(visual_statuses, duration_value),
                source_sheet_title=spreadsheet.title,
                source_worksheet_title=worksheet.title,
            )
            if self._is_omit_shot(shot_summary):
                continue

            shots.append(shot_summary)

        return shots

    def _fetch_shots_from_visual_review(
        self,
        spreadsheet: gspread.Spreadsheet,
        worksheet: gspread.Worksheet,
        scene_code: str | None,
        fallback_previews: dict[str, tuple[str, bytes]] | None = None,
        ani_task_statuses: dict[str, list[GoogleShotTaskStatus]] | None = None,
    ) -> list[GoogleShotSummary]:
        display_rows = worksheet.get_all_values()
        formula_rows = worksheet.get("A1:C400", value_render_option=ValueRenderOption.formula)
        embedded_previews = {}
        if self.settings.cache_sheet_previews:
            embedded_previews = self._extract_embedded_previews_from_xlsx(
                spreadsheet.id,
                worksheet.id,
                worksheet.title,
                scene_code,
                display_rows,
            )

        if len(display_rows) < 5:
            return []

        task_columns = self._extract_visual_review_task_columns(display_rows)
        shots: list[GoogleShotSummary] = []
        for row_index in range(4, len(display_rows)):
            row = display_rows[row_index]
            shot_value = self._string_or_none(self._get_by_index(row, 0))
            if not shot_value or self._contains_omit(shot_value):
                continue
            if not self._has_meaningful_shot_row(row, detail_start_col=2):
                continue

            duration_value = self._get_by_index(row, 2)
            formula_row = formula_rows[row_index] if row_index < len(formula_rows) else []
            preview_formula = self._get_by_index(formula_row, 1)
            normalized_shot_code = self._normalize_shot_code(scene_code, shot_value)
            preview_image_url = self._extract_image_url(preview_formula, self._get_by_index(row, 1))
            if self.settings.cache_sheet_previews:
                cache_preview_image(scene_code, normalized_shot_code, preview_image_url)
                if not preview_image_url and fallback_previews and normalized_shot_code in fallback_previews:
                    image_name, image_data = fallback_previews[normalized_shot_code]
                    cache_preview_bytes(scene_code, normalized_shot_code, image_name, image_data)
                elif not preview_image_url and row_index in embedded_previews:
                    image_name, image_data = embedded_previews[row_index]
                    cache_preview_bytes(scene_code, normalized_shot_code, image_name, image_data)

            visual_statuses = [
                GoogleShotTaskStatus(
                    task_key=task["task_key"],
                    label=task["label"],
                    artist=self._string_or_none(self._get_by_index(row, task["artist_col"])),
                    status=self._normalize_visual_status_value(self._get_by_index(row, task["status_col"])),
                )
                for task in task_columns
            ]
            if ani_task_statuses and normalized_shot_code in ani_task_statuses:
                visual_statuses = ani_task_statuses[normalized_shot_code] + visual_statuses

            shot_summary = GoogleShotSummary(
                shot_code=normalized_shot_code,
                duration_frames=self._int_or_none(self._normalize_int_string(duration_value)),
                preview_image_url=preview_image_url,
                cam=self._string_or_none(self._get_by_index(row, 3)),
                visual_statuses=visual_statuses,
                shot_level=self._calculate_shot_level(visual_statuses, duration_value),
                source_sheet_title=spreadsheet.title,
                source_worksheet_title=worksheet.title,
            )
            if self._is_omit_shot(shot_summary):
                continue

            shots.append(shot_summary)

        return shots

    def _cache_scene_preview_sheet(
        self,
        spreadsheet_id: str,
        worksheet: gspread.Worksheet,
        scene_code: str | None,
        target_shot_code: str | None = None,
    ) -> Path | None:
        display_rows = worksheet.get_all_values()
        if len(display_rows) < 5:
            return None

        formula_rows = worksheet.get("A1:C400", value_render_option=ValueRenderOption.formula)
        row_lookup: dict[str, int] = {}
        for row_index in range(4, len(display_rows)):
            row = display_rows[row_index]
            shot_value = self._string_or_none(self._get_by_index(row, 0))
            if not shot_value or self._contains_omit(shot_value):
                continue
            normalized_shot_code = self._normalize_shot_code(scene_code, shot_value)
            row_lookup[normalized_shot_code] = row_index

            formula_row = formula_rows[row_index] if row_index < len(formula_rows) else []
            preview_formula = self._get_by_index(formula_row, 1)
            preview_image_url = self._extract_image_url(preview_formula, self._get_by_index(row, 1))
            if preview_image_url:
                cache_preview_image(scene_code, normalized_shot_code, preview_image_url)

        if target_shot_code:
            cached = find_cached_preview(scene_code or "", target_shot_code)
            if cached is not None:
                return cached

        embedded_previews = self._extract_embedded_previews_from_xlsx(
            spreadsheet_id,
            worksheet.id,
            worksheet.title,
            scene_code,
            display_rows,
        )
        for normalized_shot_code, row_index in row_lookup.items():
            if row_index not in embedded_previews:
                continue
            image_name, image_data = embedded_previews[row_index]
            cache_preview_bytes(scene_code, normalized_shot_code, image_name, image_data)

        if target_shot_code:
            return find_cached_preview(scene_code or "", target_shot_code)
        return None

    def _extract_ani_task_statuses(
        self,
        spreadsheet: gspread.Spreadsheet,
        scene_code: str | None,
    ) -> dict[str, list[GoogleShotTaskStatus]]:
        worksheet = self._get_scene_worksheet(spreadsheet, scene_code, "Ani_Review Note")
        if worksheet is None:
            return {}

        rows = worksheet.get_all_values()
        if len(rows) < 4:
            return {}

        task_defs = [
            ("ani_dt", "ANI DT", 6),
            ("ani_pl", "ANI PL", 7),
            ("ani_ao", "ANI AO", 8),
        ]
        statuses: dict[str, list[GoogleShotTaskStatus]] = {}
        for row in rows[3:]:
            shot_value = self._string_or_none(self._get_by_index(row, 0))
            if not shot_value or self._contains_omit(shot_value):
                continue

            normalized_shot_code = self._normalize_shot_code(scene_code, shot_value)
            statuses[normalized_shot_code] = [
                GoogleShotTaskStatus(
                    task_key=task_key,
                    label=label,
                    artist=self._string_or_none(self._get_by_index(row, 4)),
                    status=self._normalize_visual_status_value(self._get_by_index(row, status_col)),
                )
                for task_key, label, status_col in task_defs
            ]

        return statuses

    def _extract_visual_review_task_columns(self, rows: list[list[str]]) -> list[dict]:
        if len(rows) < 3:
            return []

        task_row = rows[1]
        header_row = rows[2]
        task_columns: list[dict] = []
        for index, header in enumerate(header_row):
            if str(header).strip().lower() != "artist":
                continue
            next_header = self._get_by_index(header_row, index + 1)
            if str(next_header).strip().lower() != "st":
                continue

            label = self._string_or_none(self._get_by_index(task_row, index)) or f"Task {len(task_columns) + 1}"
            task_columns.append(
                {
                    "task_key": self._slugify(label),
                    "label": label,
                    "artist_col": index,
                    "status_col": index + 1,
                }
            )

        return task_columns

    def _detail_worksheets(
        self,
        spreadsheet: gspread.Spreadsheet,
        scene_code: str | None,
    ) -> list[gspread.Worksheet]:
        worksheets: list[gspread.Worksheet] = []
        for suffix in ("Direction Note", "Vis_Review Note"):
            worksheet = self._get_scene_worksheet(spreadsheet, scene_code, suffix)
            if worksheet is not None and worksheet.id not in {item.id for item in worksheets}:
                worksheets.append(worksheet)
        return worksheets

    def _find_shot_detail_columns(self, header_rows: list[list[str]]) -> dict[str, int | None]:
        shot_description_col = self._find_keyword_column(header_rows, "shot description")
        direction_note_col = self._find_keyword_column(header_rows, "direction note")
        max_col = max((len(row) for row in header_rows), default=0) - 1
        if (
            direction_note_col is not None
            and shot_description_col is not None
            and direction_note_col - 1 == shot_description_col
            and direction_note_col < max_col
        ):
            direction_note_col += 1
        retake_note_col = direction_note_col + 1 if direction_note_col is not None and direction_note_col < max_col else None
        return {
            "shot_description": shot_description_col,
            "direction_note": direction_note_col,
            "retake_note": retake_note_col,
        }

    def _find_keyword_column(self, rows: list[list[str]], keyword: str) -> int | None:
        normalized_keyword = self._normalize_header_text(keyword)
        for row in rows:
            for index, cell in enumerate(row):
                if normalized_keyword in self._normalize_header_text(cell):
                    return index
        return None

    @staticmethod
    def _normalize_header_text(value: str | None) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    def _extract_embedded_previews_from_xlsx(
        self,
        spreadsheet_id: str,
        worksheet_gid: int | None,
        worksheet_title: str,
        scene_code: str | None,
        display_rows: list[list[str]],
    ) -> dict[int, tuple[str, bytes]]:
        try:
            xlsx_data = self._export_worksheet_xlsx(spreadsheet_id, worksheet_gid) if worksheet_gid is not None else self._export_spreadsheet_xlsx(spreadsheet_id)
            row_media = self._read_embedded_images_by_row(xlsx_data, worksheet_title, target_col=1)
        except Exception:
            return {}

        previews: dict[int, tuple[str, bytes]] = {}
        for row_index in range(4, len(display_rows)):
            row = display_rows[row_index]
            shot_value = self._string_or_none(self._get_by_index(row, 0))
            if not shot_value or self._contains_omit(shot_value):
                continue
            if row_index in row_media:
                previews[row_index] = row_media[row_index]
        return previews

    def _extract_embedded_previews_by_shot_code(
        self,
        spreadsheet_id: str,
        worksheet_gid: int | None,
        worksheet_title: str,
        scene_code: str | None,
        display_rows: list[list[str]],
    ) -> dict[str, tuple[str, bytes]]:
        if not worksheet_title or not display_rows:
            return {}

        row_previews = self._extract_embedded_previews_from_xlsx(
            spreadsheet_id,
            worksheet_gid,
            worksheet_title,
            scene_code,
            display_rows,
        )
        previews: dict[str, tuple[str, bytes]] = {}
        for row_index, media in row_previews.items():
            shot_value = self._string_or_none(self._get_by_index(display_rows[row_index], 0))
            if not shot_value:
                continue
            shot_code = self._normalize_shot_code(scene_code, shot_value)
            previews[shot_code] = media
        return previews

    def _export_spreadsheet_xlsx(self, spreadsheet_id: str) -> bytes:
        credentials = self._get_credentials()
        credentials.refresh(GoogleAuthRequest())
        export_url = (
            f"https://www.googleapis.com/drive/v3/files/{spreadsheet_id}/export"
            "?mimeType=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        request = UrlRequest(
            export_url,
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        with urlopen(request, timeout=30) as response:
            return response.read()

    def _export_worksheet_xlsx(self, spreadsheet_id: str, worksheet_gid: int) -> bytes:
        credentials = self._get_credentials()
        credentials.refresh(GoogleAuthRequest())
        export_url = (
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export"
            f"?format=xlsx&single=true&gid={worksheet_gid}"
        )
        request = UrlRequest(
            export_url,
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "User-Agent": "SFVisualPreviewCache/1.0",
            },
        )
        with urlopen(request, timeout=30) as response:
            return response.read()

    def _read_embedded_images_by_row(
        self,
        xlsx_data: bytes,
        worksheet_title: str,
        target_col: int,
    ) -> dict[int, tuple[str, bytes]]:
        with zipfile.ZipFile(BytesIO(xlsx_data)) as archive:
            worksheet_path = self._find_xlsx_worksheet_path(archive, worksheet_title)
            if not worksheet_path:
                return {}

            drawing_path = self._find_xlsx_drawing_path(archive, worksheet_path)
            if not drawing_path:
                return {}

            drawing_rels = self._read_xlsx_rels(archive, self._rels_path(drawing_path))
            drawing_root = ET.fromstring(archive.read(drawing_path))
            namespaces = {
                "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
                "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
                "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            }

            images: dict[int, tuple[str, bytes]] = {}
            anchors = list(drawing_root.findall("xdr:twoCellAnchor", namespaces))
            anchors.extend(drawing_root.findall("xdr:oneCellAnchor", namespaces))
            for anchor in anchors:
                from_node = anchor.find("xdr:from", namespaces)
                if from_node is None:
                    continue
                col = self._int_or_none(from_node.findtext("xdr:col", default="", namespaces=namespaces))
                row = self._int_or_none(from_node.findtext("xdr:row", default="", namespaces=namespaces))
                if col != target_col or row is None:
                    continue

                blip = anchor.find(".//a:blip", namespaces)
                rel_id = blip.attrib.get(f"{{{namespaces['r']}}}embed") if blip is not None else None
                if not rel_id or rel_id not in drawing_rels:
                    continue

                media_path = self._resolve_xlsx_target(drawing_path, drawing_rels[rel_id])
                if media_path not in archive.namelist():
                    continue
                images[row] = (Path(media_path).name, archive.read(media_path))
            return images

    def _find_xlsx_worksheet_path(self, archive: zipfile.ZipFile, worksheet_title: str) -> str | None:
        workbook_path = "xl/workbook.xml"
        workbook_rels_path = "xl/_rels/workbook.xml.rels"
        if workbook_path not in archive.namelist() or workbook_rels_path not in archive.namelist():
            return None

        workbook_root = ET.fromstring(archive.read(workbook_path))
        workbook_rels = self._read_xlsx_rels(archive, workbook_rels_path)
        namespaces = {
            "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }
        fallback_path = None
        for sheet in workbook_root.findall(".//main:sheet", namespaces):
            rel_id = sheet.attrib.get(f"{{{namespaces['r']}}}id")
            target = workbook_rels.get(rel_id or "")
            if target and fallback_path is None:
                fallback_path = self._resolve_xlsx_target(workbook_path, target)
            if self._normalize_title_for_match(sheet.attrib.get("name")) == self._normalize_title_for_match(worksheet_title):
                if target:
                    return self._resolve_xlsx_target(workbook_path, target)
        return None

    def _find_xlsx_drawing_path(self, archive: zipfile.ZipFile, worksheet_path: str) -> str | None:
        rels_path = self._rels_path(worksheet_path)
        if rels_path not in archive.namelist():
            return None

        rels = self._read_xlsx_rels(archive, rels_path)
        worksheet_root = ET.fromstring(archive.read(worksheet_path))
        namespaces = {
            "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }
        drawing = worksheet_root.find("main:drawing", namespaces)
        if drawing is None:
            return None
        rel_id = drawing.attrib.get(f"{{{namespaces['r']}}}id")
        target = rels.get(rel_id or "")
        if not target:
            return None
        return self._resolve_xlsx_target(worksheet_path, target)

    @staticmethod
    def _read_xlsx_rels(archive: zipfile.ZipFile, rels_path: str) -> dict[str, str]:
        if rels_path not in archive.namelist():
            return {}
        root = ET.fromstring(archive.read(rels_path))
        relationships: dict[str, str] = {}
        for rel in root:
            rel_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target")
            if rel_id and target:
                relationships[rel_id] = target
        return relationships

    @staticmethod
    def _rels_path(part_path: str) -> str:
        directory, name = posixpath.split(part_path)
        return posixpath.join(directory, "_rels", f"{name}.rels")

    @staticmethod
    def _resolve_xlsx_target(source_path: str, target: str) -> str:
        if target.startswith("/"):
            return target.lstrip("/")
        source_dir = posixpath.dirname(source_path)
        return posixpath.normpath(posixpath.join(source_dir, target))

    @staticmethod
    def _get_scene_worksheet(
        spreadsheet: gspread.Spreadsheet,
        scene_code: str | None,
        suffix: str,
    ) -> gspread.Worksheet | None:
        if scene_code:
            try:
                return spreadsheet.worksheet(f"{scene_code}_{suffix}")
            except gspread.WorksheetNotFound:
                pass

        suffix_normalized = suffix.lower()
        for worksheet in spreadsheet.worksheets():
            if worksheet.title.lower().endswith(suffix_normalized):
                return worksheet
        return None

    @staticmethod
    def _get_direction_worksheet(
        spreadsheet: gspread.Spreadsheet,
        scene_code: str | None,
    ) -> gspread.Worksheet | None:
        if scene_code:
            try:
                return spreadsheet.worksheet(f"{scene_code}_Direction Note")
            except gspread.WorksheetNotFound:
                pass
        return spreadsheet.get_worksheet(0)

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).strip().lower())
        return normalized.strip("_") or "task"

    @staticmethod
    def _normalize_shot_code(scene_code: str | None, shot_value: str) -> str:
        if not scene_code:
            return shot_value
        if re.match(r"^\d{4}_", shot_value):
            return shot_value
        if shot_value.startswith(f"{scene_code}_"):
            return shot_value
        return f"{scene_code}_{shot_value}"

    @staticmethod
    def _normalize_title_for_match(value: str | None) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", str(value or "")).lower()

    @staticmethod
    def _normalize_scene_code(scene_code: str | None) -> str | None:
        if not scene_code:
            return scene_code
        match = re.search(r"\d{4}", str(scene_code))
        return match.group(0) if match else str(scene_code)

    @staticmethod
    def _extract_image_url(*values: str | None) -> str | None:
        for value in values:
            if not value:
                continue
            match = re.search(r'IMAGE\(\s*"([^"]+)"', str(value), re.IGNORECASE)
            if match:
                return match.group(1)
            url_match = re.search(r"https?://[^\s\"')]+", str(value))
            if url_match:
                return url_match.group(0)
        return None

    @staticmethod
    def _contains_omit(value: str | None) -> bool:
        if not value:
            return False
        normalized = str(value).strip().lower()
        return any(keyword in normalized for keyword in OMIT_KEYWORDS)

    def _is_omit_row(self, row: list[str]) -> bool:
        return any(self._contains_omit(cell) for cell in row)

    def _has_meaningful_shot_row(self, row: list[str], detail_start_col: int = 2) -> bool:
        for cell in row[detail_start_col:]:
            text = self._string_or_none(cell)
            if text and not self._contains_omit(text):
                return True
        return False

    def _normalize_visual_status_value(self, value: str | None) -> str | None:
        text = self._string_or_none(value)
        if text is None:
            return None
        if text.lower() == "none":
            return "app"
        return text

    def _calculate_shot_level(
        self,
        visual_statuses: list[GoogleShotTaskStatus],
        duration_value: str | int | None,
    ) -> GoogleShotLevel:
        water_task = next(
            (
                task
                for task in visual_statuses
                if re.search(r"water", f"{task.label} {task.task_key}", re.IGNORECASE)
            ),
            None,
        )
        water_level = self._parse_water_level(water_task.artist if water_task else None)
        duration_frames = self._int_or_none(self._normalize_int_string(duration_value)) or 0
        duration_weight = self._duration_weight(duration_frames)
        base_score = 1 + water_level
        score = round(base_score + duration_weight, 2)
        staff_days = round(score * STAFF_DAYS_PER_LEVEL_SCORE, 2)
        lead_days = round(score * LEAD_DAYS_PER_LEVEL_SCORE, 2)
        water_labels = {
            0: "Normal Render",
            1: "Water LV1",
            2: "Water LV2 + 2D FX",
            3: "Water LV3 + 2D FX",
        }
        level_labels = {
            0: "L0 Normal",
            1: "L1 Calm Water",
            2: "L2 Splash Water",
            3: "L3 Hero Water",
        }
        return GoogleShotLevel(
            water_level=water_level,
            water_label=water_labels[water_level],
            duration_weight=duration_weight,
            score=score,
            staff_days=staff_days,
            lead_days=lead_days,
            label=level_labels[water_level],
        )

    @staticmethod
    def _parse_water_level(value: str | None) -> int:
        if not value:
            return 0

        normalized = str(value).lower()
        for level in (3, 2, 1):
            if re.search(
                rf"(?:(?:lv|level|\ub808\ubca8|\ub808\ubc8c)[\W_]*{level}|{level}[\W_]*\ub2e8\uacc4)",
                normalized,
            ):
                return level
        return 0

    @staticmethod
    def _duration_weight(duration_frames: int) -> float:
        if duration_frames <= 0:
            return 0
        return round(min(duration_frames / 96, 2), 2)

    def _is_omit_scene(self, scene: GoogleSceneSummary) -> bool:
        return any(
            self._contains_omit(candidate)
            for candidate in [scene.scene_code, scene.scene_label, scene.shotlist_name]
        )

    def _is_omit_shot(self, shot: GoogleShotSummary) -> bool:
        render_or_comp = [
            task
            for task in shot.visual_statuses
            if re.search(r"render|composit", f"{task.label} {task.task_key}", re.IGNORECASE)
        ]
        if any(self._contains_omit(task.status) for task in render_or_comp):
            return True

        return any(
            self._contains_omit(candidate)
            for candidate in [shot.shot_code, shot.source_sheet_title, shot.source_worksheet_title]
        )
