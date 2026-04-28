from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.health import router as health_router
from app.api.routes.google_sheets import router as google_sheets_router
from app.api.routes.local_media import router as local_media_router
from app.api.routes.shots import router as shots_router
from app.api.routes.sync import router as sync_router
from app.config import get_settings
from app.db import Base, engine


settings = get_settings()
app = FastAPI(title=settings.app_name)
frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "mockup"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(google_sheets_router, prefix=settings.api_prefix)
app.include_router(local_media_router, prefix=settings.api_prefix)
app.include_router(shots_router, prefix=settings.api_prefix)
app.include_router(sync_router, prefix=settings.api_prefix)

if frontend_dir.exists():
    app.mount("/sfvisual", StaticFiles(directory=frontend_dir, html=True), name="sfvisual")


@app.get("/", include_in_schema=False)
def read_root() -> RedirectResponse:
    return RedirectResponse(url="/sfvisual/")
