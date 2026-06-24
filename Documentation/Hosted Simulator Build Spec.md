# Hosted Simulator Build Specification (v1)

## Purpose

Define the implementation blueprint for converting the current browser-executed simulator into a hosted web application where:

- the browser is only a control/UI client,
- simulation execution runs on the simulator service,
- all state is persistent and recoverable,
- multiple concurrent runs can target multiple Safe Signal environments.

This document is the source of truth for v1 scope and technical decisions.

## Confirmed Product Decisions

1. Authentication for simulator users is local (simulator-managed users table).
2. Seed one admin user; users can create/manage other users.
3. All users have full simulator control (no RBAC in v1).
4. Single tenancy.
5. SQLite for v1, with SQLAlchemy + Alembic so migration to another DB is straightforward.
6. Environment credentials are system-wide, not per-user.
7. Environment username may be displayed; password is never revealed after save.
8. Environment credentials may require 2FA.
9. Simulations are user-initiated start/stop only in v1 (no scheduled starts/stops yet).
10. Default teardown behavior is cleanup via close -> archive -> delete.
11. Separate feature: synthetic case generation without simulation and without mandatory teardown.

## Confirmed Extension Decisions (Case Worker Load)

1. Add a second run/profile mode for case-worker load simulation.
2. Case-worker runs are always child runs of an existing telemetry run.
3. Child runs may only target cases owned by the parent telemetry run.
4. Parent telemetry runs cannot be stopped while child case-worker runs are active.
5. Child runs must stop (or be force-stopped by policy endpoint in future versions) before parent stop is allowed.
6. Child write operations must enforce immutable telemetry-critical fields:
   - enrollment details / activation pin,
   - phone/device identifier,
   - device API key,
   - status transitions that break device telemetry lifecycle.
7. Child runs expose throughput metrics as logical transaction counters/rates.

## High-Level Architecture

### Components

1. **Simulator API Service (FastAPI)**
   - Auth/session endpoints for simulator users.
   - Environment, run, and operations endpoints.
   - Dashboard and event query endpoints.

2. **Worker/Scheduler Runtime (in-process for v1)**
   - Drives run orchestration and per-case simulation loops.
   - Maintains persistent state machine in DB.
   - Handles retry/backoff and crash recovery.

3. **Persistence Layer**
   - SQLite in WAL mode.
   - SQLAlchemy ORM models.
   - Alembic migrations for schema lifecycle.

4. **Hosted Frontend**
   - Browser UI calls simulator API only.
   - No direct browser calls to Safe Signal APIs.

### Deployment Model (v1)

- Single Python process for local development and first hosted deployment.
- Container-ready packaging, but Docker runtime is not mandatory for first milestone.
- Future-ready to split API and worker into separate processes without domain model changes.

## Technical Stack

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- SQLite (with upgrade path to PostgreSQL)
- Passlib/Bcrypt for password hashing
- Pydantic for request/response schemas
- HTTPX for Safe Signal API client

## Domain Model (Initial Schema)

Note: names are implementation suggestions; exact naming can follow project conventions.

### `users`

- `id` (pk)
- `email` (unique, indexed)
- `password_hash`
- `is_active` (bool)
- `is_admin` (bool; all users full-control, admin only required for bootstrap/user management)
- `created_at`, `updated_at`, `last_login_at`

### `environments`

- `id` (pk)
- `name` (unique)
- `base_url`
- `api_username`
- `encrypted_api_password`
- `credential_version` (int, increments on password change)
- `auth_mode` (enum: `password_only`, `password_plus_2fa`, `auto_detect`)
- `is_active` (bool)
- `last_auth_ok_at`
- `last_auth_error`
- `created_at`, `updated_at`

### `environment_auth_sessions`

- `id` (pk)
- `environment_id` (fk)
- `state` (enum: `valid`, `expired`, `challenge_required`, `failed`)
- `encrypted_session_blob` (cookies/tokens)
- `expires_at`
- `challenge_type` (nullable, e.g. `otp`)
- `challenge_context` (nullable JSON)
- `last_attempt_at`
- `last_success_at`

### `run_profiles`

- `id` (pk)
- `name`
- `device_count_initial`
- `update_min_ms`, `update_max_ms`
- `activation_chance`
- `active_interval_ms`
- `active_duration_ms`
- `case_creation_delay_ms`
- `teardown_mode` (enum: `delete`, `archive`)
- `profile_kind` (enum: `device_telemetry`, `case_worker`)
- `caseworker_worker_count_initial`
- `caseworker_actions_per_min_per_worker`
- `caseworker_think_time_min_ms`, `caseworker_think_time_max_ms`
- `caseworker_read_ratio` (0.0-1.0, remaining traffic is write attempts)
- `created_by_user_id` (fk)
- `created_at`, `updated_at`

### `runs`

- `id` (pk)
- `environment_id` (fk)
- `profile_id` (fk, nullable snapshot strategy allowed)
- `status` (enum: `starting`, `running`, `scaling`, `stopping`, `stopped`, `action_required`, `error`)
- `run_kind` (enum: `device_telemetry`, `case_worker`)
- `parent_run_id` (nullable fk to `runs.id`, required for `case_worker`)
- `blocked_reason` (nullable enum/text, e.g. `env_2fa_required`)
- `desired_case_count`
- `active_case_count`
- `actions_total`
- `actions_failed_total`
- `actions_per_second_current`
- `actions_per_second_avg`
- `created_by_user_id` (fk)
- `started_at`, `stopped_at`, `created_at`, `updated_at`

### `run_cases`

- `id` (pk)
- `run_id` (fk)
- `environment_id` (fk)
- `safe_signal_case_id`
- `device_id`
- `device_api_key`
- `state` (enum: `provisioning`, `active`, `scale_down_pending`, `teardown_pending`, `teardown_blocked_auth`, `teardown_failed`, `teardown_done`)
- `next_update_at`
- `last_update_at`
- `last_error`
- `schedule_overrides` (nullable JSON for case-specific params)
- `created_at`, `updated_at`

### `run_events`

- `id` (pk)
- `run_id` (fk)
- `run_case_id` (nullable fk)
- `environment_id` (fk)
- `level` (enum: `info`, `warning`, `error`)
- `event_type` (string)
- `message`
- `payload` (nullable JSON)
- `created_at`

### `synthetic_generation_jobs`

- `id` (pk)
- `environment_id` (fk)
- `status` (enum: `queued`, `running`, `completed`, `failed`, `cancelled`)
- `requested_case_count`
- `created_case_count`
- `teardown_mode` (nullable; may be `none`)
- `created_by_user_id` (fk)
- `started_at`, `completed_at`, `created_at`, `updated_at`

### `worker_leases`

- `id` (pk)
- `worker_name`
- `lease_owner`
- `lease_expires_at`
- `heartbeat_at`

Used to ensure only one active scheduler loop in multi-process future deployments.

## API Surface (v1)

### Auth

- `POST /api/sim/auth/login`
- `POST /api/sim/auth/logout`
- `GET /api/sim/auth/me`

### User Management

- `GET /api/sim/users`
- `POST /api/sim/users`
- `PATCH /api/sim/users/{id}`
- `POST /api/sim/users/{id}/reset-password`

### Environments

- `GET /api/sim/environments`
- `POST /api/sim/environments`
- `GET /api/sim/environments/{id}`
- `PATCH /api/sim/environments/{id}`
  - Password update is write-only.
  - Empty password means "keep current".
- `POST /api/sim/environments/{id}/test-auth`
- `POST /api/sim/environments/{id}/2fa/submit`

### Profiles

- `GET /api/sim/profiles`
- `POST /api/sim/profiles`
- `PATCH /api/sim/profiles/{id}`
- `DELETE /api/sim/profiles/{id}`

### Runs

- `GET /api/sim/runs`
- `POST /api/sim/runs` (start; case-worker runs must include `parent_run_id`)
- `GET /api/sim/runs/{id}`
- `POST /api/sim/runs/{id}/stop` (parent run stop blocked while child run active)
- `POST /api/sim/runs/{id}/scale` (`delta_cases`: +N/-N)
- `POST /api/sim/runs/{id}/resume` (if action required or recoverable)

### Run Operations/Visibility

- `GET /api/sim/runs/{id}/cases`
- `GET /api/sim/runs/{id}/events`
- `GET /api/sim/dashboard/summary`
- `GET /api/sim/dashboard/challenges` (pending 2FA prompts)

### Synthetic Generation (No Ongoing Simulation)

- `POST /api/sim/synthetic-jobs`
- `GET /api/sim/synthetic-jobs`
- `GET /api/sim/synthetic-jobs/{id}`
- `POST /api/sim/synthetic-jobs/{id}/cancel`

## Safe Signal Integration Rules

The simulator service must continue to respect existing server contracts:

- Fetch genders from `GET /api/master/genders`
- Fetch case languages from `GET /api/languages?for_case=true` (not `for_interface=true`)
- Continue using current case creation, enroll, statusupdate, and teardown sequence semantics.

## Worker and State Machine Design

### Tick Loop

- Scheduler runs every short interval (e.g. 500-1000 ms).
- Pulls due work from DB (`next_update_at`, pending provisioning, pending teardown).
- Applies bounded concurrency limits globally and per environment.

### Run Start Flow

1. Validate environment and profile.
2. Ensure environment auth session is valid.
3. Provision desired initial cases:
   - create case,
   - upload photos if enabled,
   - enroll device,
   - persist device API key and next update time.
4. Transition run to `running`.

### Case Worker Child Flow

1. Validate profile kind `case_worker` and `parent_run_id`.
2. Validate parent run exists, is telemetry kind, shares the same environment, and is in `running` state.
3. Build candidate case pool from parent run owned cases only.
4. Execute weighted read/write transactions against the case pool.
5. Apply immutable field guardrails before every write transaction.
6. Emit transaction metrics (`actions_total`, failures, TPS) and event records.

### Update Flow (Per Case)

1. Calculate active/inactive mode based on profile and per-case state.
2. Send status update using `device_api_key`.
3. Persist result, error counters, next schedule time.
4. Emit event entries for notable failures.

### Scale Flow

- `+N`: enqueue provisioning jobs and increment desired count.
- `-N`: mark selected active cases `scale_down_pending`, transition to teardown queue.

### Stop Flow

1. Mark run as `stopping`.
2. Stop scheduling updates for active cases.
3. Enqueue all non-teardown-complete cases for teardown.
4. When queue drains successfully, mark run `stopped`.
5. If teardown blocked by auth/2FA, mark run `action_required` with clear reason.

### Parent/Child Interlock Rules

- Telemetry parent stop is rejected if any child case-worker run is not stopped.
- Case-worker child start is rejected unless parent is running.
- Child run transitions to `action_required` if parent is no longer running.
- Parent deletion is rejected while child runs exist.

### Teardown Strategy

- For each case attempt:
  1. fetch case,
  2. if open -> close,
  3. if closed -> archive,
  4. if delete mode -> delete archived case.
- Treat 404 as idempotent success for delete/fetch-after-delete scenarios.
- Retry with exponential backoff on transient failure.

### Reauthentication and 2FA

- Keep environment session alive in background while runs exist.
- If auth challenge occurs:
  - set `environment_auth_sessions.state=challenge_required`,
  - emit event and surface in dashboard challenges,
  - transition impacted run(s) to `action_required` only for blocked operations.
- On successful OTP submission, resume blocked work automatically.

## Security Requirements

1. Password hashing for simulator users (passlib; `pbkdf2_sha256` in v1).
2. Environment secrets encrypted at rest.
3. Never return decrypted environment password in API responses.
4. Mask secrets in logs/events.
5. Session cookies should be `HttpOnly`, `Secure` (when TLS), and SameSite policy set.

## Observability and Ops

- Run-level counters: active cases, errors, provisioned, teardown pending/failed.
- Case-worker counters: actions total, action failures, current TPS, average TPS.
- Environment-level health: auth session age, last successful auth, pending challenge.
- Event stream with searchable types and timestamps.
- Startup recovery:
  - reclaim interrupted runs,
  - resume pending teardown,
  - continue due update scheduling.

## Migration Plan from Current Codebase

### Phase 0: Bootstrap Repository Structure

- Add backend app folder (e.g. `backend/` or `simulator_service/`).
- Add dependency and startup scripts.

### Phase 1: Identity + Persistence

- Implement user auth and seeded admin.
- Introduce SQLAlchemy models and Alembic baseline migration.
- Add environment CRUD with write-only password update semantics.

### Phase 2: Safe Signal Client + Auth Session Manager

- Port API integration logic from browser JS into Python client.
- Add environment session persistence and keepalive.
- Add 2FA challenge handling endpoints.

### Phase 3: Run Engine

- Implement run/profile CRUD and worker tick loop.
- Implement case provisioning, update sending, and teardown queue.
- Implement scale in/out operations.

### Phase 4: Hosted UI

- Replace direct browser orchestration with simulator API calls.
- Add dashboard by environment and run.
- Add pending 2FA challenge actions.

### Phase 5: Packaging + Hardening

- Add Dockerfile and environment-variable configuration.
- Add startup checks and migration automation guidance.
- Add integration tests for run lifecycle and teardown reliability.

## Non-Goals for v1

- Per-user permission models and run ownership restrictions.
- Scheduled/cron-like automatic run starts/stops.
- Full multi-tenant segregation.
- Distributed queue/worker cluster orchestration.

## Acceptance Criteria (v1)

1. A simulator user can log in and start/stop runs from hosted UI.
2. Multiple runs can operate concurrently across multiple environments.
3. Runs persist through browser refresh and process restart.
4. Scale operations (`+/- N`) work while run is active.
5. Teardown defaults to delete and survives transient failures.
6. 2FA-required reauth is surfaced and resumable without data loss.
7. Existing master data rules are preserved (`genders`, `languages?for_case=true`).

## Immediate Next Implementation Tasks

1. Create backend project skeleton and dependency manifest.
2. Add SQLAlchemy base models + Alembic init and first migration.
3. Implement auth (seed admin, login/logout/me).
4. Implement environments CRUD with encrypted credential storage.
5. Implement Safe Signal auth test endpoint and 2FA submission flow.
