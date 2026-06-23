# Simulator Backend (Phase 1)

This folder contains the hosted simulator backend scaffold.

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r backend/requirements.txt`
3. Set optional env vars (or use defaults):
   - `SIM_DATABASE_URL` (default: `sqlite:///backend/data/simulator.db`)
   - `SIM_SECRET_KEY` (set this in real deployments)
   - `SIM_SEED_ADMIN_EMAIL` (default: `admin@perfsim.local`)
   - `SIM_SEED_ADMIN_PASSWORD` (default: `ChangeMeNow123!`)
4. Run migrations:
   - `alembic -c backend/alembic.ini upgrade head`
5. Start API:
   - `uvicorn app.main:app --reload --app-dir backend --host 0.0.0.0 --port 7999`

## Smoke check

Run:

- `python backend/scripts/smoke_check.py`

This verifies app boot and health endpoint wiring.

## First endpoints to try

- `http://localhost:7999/` (API info)
- `http://localhost:7999/health`
- `http://localhost:7999/docs`
- `http://localhost:7999/console` (hosted web console)

## Current phase endpoints

- `POST /api/sim/auth/login`
- `POST /api/sim/auth/logout`
- `GET /api/sim/auth/me`
- `GET/POST/PATCH/DELETE /api/sim/environments`
- `POST /api/sim/environments/{id}/test-auth`
- `POST /api/sim/environments/{id}/2fa/submit`
- `GET/POST/PATCH/DELETE /api/sim/profiles`
- `GET/POST /api/sim/runs`
- `GET /api/sim/runs/{id}`
- `GET /api/sim/runs/{id}/events`
- `GET /api/sim/runs/{id}/cases`
- `POST /api/sim/runs/{id}/stop`
- `POST /api/sim/runs/{id}/scale`
- `POST /api/sim/runs/{id}/resume`
- `DELETE /api/sim/runs/{id}`

## Worker scaffold behavior

- A lightweight in-process worker runs on startup and reconciles run case shells.
- For `running` and `action_required` runs, it moves `active_case_count` toward `desired_case_count`.
- New cases are now provisioned against the selected environment (`/api/cases` + `/api/devices/enroll`).
- Master data and organisation lookups are fetched per environment session and cached separately per environment.
- Scale-down and stop operations enqueue cases for teardown.
- Teardown now attempts close -> archive -> delete (or archive-only depending on profile teardown mode).
- Teardown retries use backoff and can mark runs `action_required` when environment auth blocks cleanup.
- Runs track basic API performance counters (`api_calls_total`, failed count, avg ms, last ms).
