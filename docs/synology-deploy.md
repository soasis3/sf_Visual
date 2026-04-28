# Synology Deploy

## Target URL

- App: `https://storyfarm1.synology.me:7000/sfvisual/`
- API: `https://storyfarm1.synology.me:7000/api/v1/`

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

## GitHub Actions auto deploy

This repository includes:

- Workflow: `.github/workflows/deploy-nas.yml`

This workflow uses a standard GitHub-hosted Linux runner and deploys to the NAS over SSH.

### One-time setup

1. Create an SSH key pair for GitHub Actions.
2. Add the public key to the NAS user account's `~/.ssh/authorized_keys`.
3. In the GitHub repository, open `Settings -> Secrets and variables -> Actions` and add:

- `NAS_HOST`
- `NAS_PORT`
- `NAS_USER`
- `NAS_SSH_KEY`

`NAS_SSH_KEY` should contain the private key text.

### Deploy behavior

On every push to `master`, GitHub Actions will:

1. SSH into the NAS
2. go to `/volume1/MACARON/RND/SFtools/sfShotManager/app/sfVisual_git`
3. run `git pull origin master`
4. run `sudo docker-compose up -d --build`

That means deployment becomes:

```text
git push -> GitHub Actions -> SSH to NAS -> deploy
```

## Reverse proxy

- Source: `HTTPS` / `storyfarm1.synology.me` / `7000`
- Destination: `HTTP` / `127.0.0.1` / `8000`

The FastAPI app serves the frontend at `/sfvisual/` and redirects `/` to `/sfvisual/`.
