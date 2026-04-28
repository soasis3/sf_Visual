from pydantic import BaseModel, Field


class GoogleShotTaskStatus(BaseModel):
    task_key: str
    label: str
    artist: str | None = None
    status: str | None = None


class GoogleShotLevel(BaseModel):
    water_level: int = 0
    water_label: str
    duration_weight: float = 0
    score: float
    staff_days: float = 0
    lead_days: float = 0
    label: str


class GoogleShotSummary(BaseModel):
    shot_code: str
    duration_frames: int | None = None
    preview_image_url: str | None = None
    cam: str | None = None
    shot_description: str | None = None
    direction_lighting: str | None = None
    retake_note: str | None = None
    visual_statuses: list[GoogleShotTaskStatus] = Field(default_factory=list)
    shot_level: GoogleShotLevel | None = None
    source_sheet_title: str
    source_worksheet_title: str


class GoogleSceneSummary(BaseModel):
    scene_code: str
    scene_label: str | None = None
    shotlist_name: str | None = None
    shotlist_url: str
    shotlist_spreadsheet_id: str
    compositing_progress: float | None = None
    total_shots: int | None = None
    total_minutes: float | None = None
    total_seconds: float | None = None
    total_frames: int | None = None
    shots: list[GoogleShotSummary] = []


class GoogleSceneListResponse(BaseModel):
    spreadsheet_title: str
    worksheet_title: str
    scenes: list[GoogleSceneSummary]
