# Synology Deploy

## Target URL

- App: `https://storyfarm1.synology.me:5006/sfvisual/`
- API: `https://storyfarm1.synology.me:5006/api/v1/`

## Minimal NAS layout

```text
/volume1/MACARON/RND/SFtools/sfShotManager
├─ app
│  └─ sfVisual
├─ data
│  ├─ db
│  └─ cache
├─ secrets
│  └─ google-service-account.json
└─ projects
   └─ theTrap
      └─ scenes
```

## Project root

- App code: `/volume1/MACARON/RND/SFtools/sfShotManager/app/sfVisual`
- Active project for now: `theTrap`
- Scene root will resolve to `/app/projects/theTrap/scenes`

## backend/.env

```env
APP_NAME=SF Visual Pipeline API
APP_ENV=production
DATABASE_URL=sqlite:////app/data/db/sf_pipeline.db
ACTIVE_PROJECT=theTrap
PROJECTS_ROOT=/app/projects
GOOGLE_SHEETS_SPREADSHEET_ID=YOUR_SPREADSHEET_ID
GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/google-service-account.json
GOOGLE_SHOTMASTER_WORKSHEET=ShotMaster
GOOGLE_SCENE_LIST_WORKSHEET=sceneList
API_PREFIX=/api/v1
SCENE_ROOT=
PREVIEW_CACHE_DIR=/app/data/cache/previews
GOOGLE_SHEETS_CACHE_DIR=/app/data/cache/google_sheets
```

`SCENE_ROOT` is left blank on purpose. When blank, the app uses:

```text
/app/projects/<ACTIVE_PROJECT>/scenes
```

## docker-compose volumes

- `/volume1/MACARON/RND/SFtools/sfShotManager/data/db:/app/data/db`
- `/volume1/MACARON/RND/SFtools/sfShotManager/data/cache:/app/data/cache`
- `/volume1/MACARON/RND/SFtools/sfShotManager/secrets:/app/secrets:ro`
- `/volume1/MACARON/RND/SFtools/sfShotManager/projects:/app/projects:ro`

The app will create its own cache subfolders inside `/app/data/cache`.

## Run

From `/volume1/MACARON/RND/SFtools/sfShotManager/app/sfVisual`:

```bash
docker-compose up -d --build
```

## Reverse proxy

- Source: `HTTPS` / `storyfarm1.synology.me` / `5006`
- Destination: `HTTP` / `127.0.0.1` / `8000`

The FastAPI app serves the frontend at `/sfvisual/` and redirects `/` to `/sfvisual/`.
