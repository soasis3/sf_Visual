from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SF Visual Pipeline API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./sf_pipeline.db"
    active_project: str = "theTrap"
    projects_root: str = ""

    google_sheets_spreadsheet_id: str = ""
    google_service_account_file: str = ""
    google_shotmaster_worksheet: str = "ShotMaster"
    google_scene_list_worksheet: str = "sceneList"
    scene_root: str = ""
    preview_cache_dir: str = ""
    google_sheets_cache_dir: str = ""
    cache_sheet_previews: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def preview_cache_path(self) -> Path:
        if self.preview_cache_dir:
            return Path(self.preview_cache_dir)
        return Path(__file__).resolve().parents[1] / ".cache" / "previews"

    @property
    def google_sheets_cache_path(self) -> Path:
        if self.google_sheets_cache_dir:
            return Path(self.google_sheets_cache_dir)
        return Path(__file__).resolve().parents[1] / ".cache" / "google_sheets"

    @property
    def projects_root_path(self) -> Path:
        if self.projects_root:
            return Path(self.projects_root)
        return Path(__file__).resolve().parents[1] / "projects"

    @property
    def scene_root_path(self) -> Path:
        if self.scene_root:
            return Path(self.scene_root)
        return self.projects_root_path / self.active_project / "scenes"


@lru_cache
def get_settings() -> Settings:
    return Settings()
