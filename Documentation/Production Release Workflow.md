# Simulator Production Release Workflow

This workflow mirrors the Safe Signal server release style but is simplified for a single hosted simulator deployment.

## Overview

- One moving release pointer branch: `prod`
- One runtime image channel: `safesignal-simulator:prod`
- One immutable release tag per build: `vX.Y.Z`

The release script builds and exports a tar from the immutable version image and also tags the same image as `:prod` for local convenience.

## 1) Ensure the working tree is clean

Release build fails when uncommitted changes exist.

```powershell
git status
```

## 2) Update the production pointer branch

Move the `prod` branch to the current commit (`HEAD`) before building.

```powershell
git push --force-with-lease origin HEAD:prod
```

## 3) Build and export the release image

Use semver bump (`patch`, `minor`, `major`) or provide an explicit version.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release-images.ps1 -Bump patch
```

Explicit version:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release-images.ps1 -Version 1.2.3
```

Artifacts are written to `exports/`:

- `safesignal-simulator-prod-vX.Y.Z.tar`
- `safesignal-simulator-image-vX.Y.Z.txt` (manifest with SHA256)

## 4) Move the tar to the runtime host

Copy the exported tar to the target runtime machine/location.

## 5) Load the image on the runtime host

```powershell
docker load -i .\exports\safesignal-simulator-prod-v1.2.3.tar
```

## 6) Update runtime env file image reference

Update `APP_IMAGE` in your runtime env file to the exact release tag:

```text
APP_IMAGE=safesignal-simulator:v1.2.3
```

Template file:

- `deployment-resources/env/prod.local.example`

## 7) Start/update the container

Compose uses the release image and runtime env settings:

```powershell
docker compose --env-file "deployment-resources/env/prod.local" -f "docker-compose.hosted.yml" -p safesignal-simulator-prod up -d --no-build
```

## Notes

- The container entrypoint runs Alembic migrations before starting the API.
- SQLite data persists in a named Docker volume mounted at `/app/backend/data`.
- Keep `SIM_SECRET_KEY` unique and strong in production env files.
- Use TLS at the proxy/load balancer and keep `SIM_SESSION_COOKIE_SECURE=true`.
