from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import json
import random
from time import perf_counter

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Environment, Run, RunCase, RunEvent
from app.services.safe_signal_runtime import (
    EnvironmentAuthChallengeError,
    EnvironmentAuthFailedError,
    authenticated_environment_client,
)


RUN_ACTIVE_STATES = {"running", "action_required", "stopping"}
RUN_CASE_ALLOCATED_STATES = {"provisioning", "provision_failed", "active"}
RUN_CASE_ACTIVE_STATES = {"active"}
RUN_CASE_TEARDOWN_QUEUE_STATES = {"teardown_pending", "teardown_failed", "teardown_blocked_auth", "scale_down_pending"}
RUN_CASE_PROVISION_QUEUE_STATES = {"provisioning", "provision_failed"}

RISK_LEVELS = ["High", "Medium", "Low"]
OS_TYPES = ["Android", "Apple"]
OFFICER_NAMES = ["Sergeant Hynes", "DS Murray", "Inspector Stratton", "PC Avery", "Lieutenant Fisher", "Supt. Blake"]
MAP_LABELS = ["PerfSim", "SafeSignal", "Control", "OpsBeat"]
FEMALE_NAMES = ["Aisling", "Ciara", "Fiona", "Maeve", "Niamh", "Aoife", "Saoirse", "Maya", "Ariana", "Leah"]
MALE_NAMES = ["Connor", "Liam", "Sean", "Eoin", "Patrick", "Declan", "Finn", "Noah", "Leo", "Ethan"]
LAST_NAMES = ["Murphy", "Kelly", "Byrne", "O'Neill", "Doyle", "Reilly", "Lynch", "Khan", "Singh", "Taylor"]
STREETS = ["Harper Lane", "Marlow Road", "Beacon Crescent", "Harrow Way", "Larkspur Drive"]
TOWNS = ["Belfast", "Galway", "Cork", "Limerick", "Brighton", "Slough", "Cardiff"]


def _pick(items: list[str]) -> str:
    return items[random.randrange(len(items))]


def _random_phone() -> str:
    return f"07{random.randint(10000000, 99999999)}"


def _random_postcode() -> str:
    areas = ["BT", "CF", "EH", "SW", "NW", "B", "M", "L", "SE", "N"]
    area = _pick(areas)
    outward = f"{area}{random.randint(1,99)}"
    inward = f"{random.randint(1,9)}{_pick(list('ABDEFGHJLNPQRSTUWXYZ'))}{_pick(list('ABDEFGHJLNPQRSTUWXYZ'))}"
    return f"{outward} {inward}"


class SimulatorWorker:
    def __init__(self, tick_seconds: float = 2.0, batch_size: int = 25) -> None:
        self.tick_seconds = tick_seconds
        self.batch_size = batch_size
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._env_context_cache: dict[int, dict[str, object]] = {}

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="simulator-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.tick_seconds)
            except TimeoutError:
                continue

    def tick(self) -> None:
        with SessionLocal() as db:
            runs = db.execute(select(Run).where(Run.status.in_(RUN_ACTIVE_STATES))).scalars().all()
            for run in runs:
                self._reconcile_run(db, run)
            db.commit()

    def _reconcile_run(self, db, run: Run) -> None:
        now = datetime.utcnow()
        desired = max(0, run.desired_case_count)
        if run.status == "stopping":
            desired = 0
            run.desired_case_count = 0

        allocated_count = (
            db.execute(
                select(func.count(RunCase.id))
                .where(RunCase.run_id == run.id)
                .where(RunCase.state.in_(RUN_CASE_ALLOCATED_STATES))
            ).scalar_one()
            or 0
        )

        if run.status == "running" and allocated_count < desired:
            create_count = min(self.batch_size, desired - allocated_count)
            for _ in range(create_count):
                db.add(
                    RunCase(
                        run_id=run.id,
                        environment_id=run.environment_id,
                        state="provisioning",
                        next_provision_at=now,
                    )
                )
            db.add(
                RunEvent(
                    run_id=run.id,
                    environment_id=run.environment_id,
                    level="info",
                    event_type="worker_provision_enqueue",
                    message=f"Worker queued {create_count} new cases for provisioning",
                )
            )

        elif allocated_count > desired:
            remove_count = min(self.batch_size, allocated_count - desired)
            candidates = (
                db.execute(
                    select(RunCase)
                    .where(RunCase.run_id == run.id)
                    .where(RunCase.state.in_(RUN_CASE_ALLOCATED_STATES))
                    .order_by(RunCase.id.desc())
                    .limit(remove_count)
                )
                .scalars()
                .all()
            )
            for run_case in candidates:
                if run_case.safe_signal_case_id:
                    run_case.state = "teardown_pending"
                    run_case.next_teardown_at = now
                else:
                    run_case.state = "teardown_done"
                    run_case.next_teardown_at = None
                run_case.last_error = None
            if candidates:
                db.add(
                    RunEvent(
                        run_id=run.id,
                        environment_id=run.environment_id,
                        level="warning",
                        event_type="worker_teardown_enqueue",
                        message=f"Worker reduced run by {len(candidates)} case allocations",
                    )
                )

        self._process_provisioning_queue(db, run)
        self._process_teardown_queue(db, run)

        active_count = (
            db.execute(
                select(func.count(RunCase.id))
                .where(RunCase.run_id == run.id)
                .where(RunCase.state.in_(RUN_CASE_ACTIVE_STATES))
            ).scalar_one()
            or 0
        )

        if run.status == "stopping":
            pending_left = (
                db.execute(
                    select(func.count(RunCase.id))
                    .where(RunCase.run_id == run.id)
                    .where(RunCase.state.in_(RUN_CASE_TEARDOWN_QUEUE_STATES.union(RUN_CASE_PROVISION_QUEUE_STATES)))
                ).scalar_one()
                or 0
            )
            if pending_left == 0 and active_count == 0:
                run.status = "stopped"
                run.stopped_at = datetime.utcnow()
                run.blocked_reason = None
                db.add(
                    RunEvent(
                        run_id=run.id,
                        environment_id=run.environment_id,
                        level="info",
                        event_type="worker_run_stopped",
                        message="All provisioning/teardown work complete; run marked stopped",
                    )
                )

        if run.status == "action_required":
            blocked_count = (
                db.execute(
                    select(func.count(RunCase.id))
                    .where(RunCase.run_id == run.id)
                    .where(RunCase.state == "teardown_blocked_auth")
                ).scalar_one()
                or 0
            )
            if blocked_count == 0:
                run.status = "running"
                run.blocked_reason = None

        run.active_case_count = active_count

    def _get_environment_context(self, db, environment: Environment) -> dict[str, object]:
        now = datetime.utcnow()
        cached = self._env_context_cache.get(environment.id)
        if cached:
            expires_at = cached.get("expires_at")
            credential_version = cached.get("credential_version")
            if isinstance(expires_at, datetime) and expires_at > now and credential_version == environment.credential_version:
                return cached

        context_data: dict[str, object] = {
            "genders": ["Female", "Male"],
            "languages": ["en-GB"],
            "organisations": [],
            "organisation_ids": [],
            "default_organisation_id": None,
            "expires_at": now + timedelta(minutes=5),
            "credential_version": environment.credential_version,
        }

        with authenticated_environment_client(db, environment) as client:
            me_payload = self._safe_get_json(client, "GET", "/api/auth/me", run=None)
            genders = self._safe_get_json(client, "GET", "/api/master/genders", run=None)
            languages = self._safe_get_json(client, "GET", "/api/languages?for_case=true", run=None)
            org_payload = self._safe_get_json(client, "GET", "/api/organisations?limit=1000", run=None)

            if isinstance(me_payload, dict) and me_payload.get("organisation_id"):
                context_data["default_organisation_id"] = me_payload.get("organisation_id")

            if isinstance(genders, list):
                names = [str(item.get("name")) for item in genders if isinstance(item, dict) and item.get("name")]
                if names:
                    context_data["genders"] = names
            if isinstance(languages, list):
                codes = [str(item.get("code")) for item in languages if isinstance(item, dict) and item.get("code")]
                if codes:
                    context_data["languages"] = codes

            organisations: list[dict[str, object]] = []
            if isinstance(org_payload, list):
                organisations = [item for item in org_payload if isinstance(item, dict)]
            elif isinstance(org_payload, dict):
                for key in ("items", "organisations", "organizations", "data", "results"):
                    candidate = org_payload.get(key)
                    if isinstance(candidate, list):
                        organisations = [item for item in candidate if isinstance(item, dict)]
                        break

            if not organisations and context_data.get("default_organisation_id") is not None:
                organisations = [{"id": context_data.get("default_organisation_id"), "name": "Default Org"}]
            context_data["organisations"] = organisations
            context_data["organisation_ids"] = [item.get("id") for item in organisations if isinstance(item, dict) and item.get("id") is not None]

        self._env_context_cache[environment.id] = context_data
        return context_data

    def _build_case_payload(self, context_data: dict[str, object], device_id: str, organisation_id: object | None) -> dict[str, object]:
        genders = context_data.get("genders") if isinstance(context_data.get("genders"), list) else ["Female", "Male"]
        gender = _pick(genders if genders else ["Female", "Male"])
        first_name = _pick(FEMALE_NAMES if gender.lower() == "female" else MALE_NAMES)
        last_name = _pick(LAST_NAMES)
        registered_user = f"{first_name} {last_name}"
        language_codes = context_data.get("languages") if isinstance(context_data.get("languages"), list) else ["en-GB"]
        language_code = _pick(language_codes if language_codes else ["en-GB"])
        review_date = (date.today() + timedelta(days=random.randint(21, 90))).isoformat()
        payload: dict[str, object] = {
            "registered_user": registered_user,
            "gender": gender,
            "risk_level": _pick(RISK_LEVELS),
            "email_address": f"{first_name.lower()}.{last_name.lower().replace(' ', '')}@perfsim.local",
            "local_reference": f"Perf-{random.randint(1000, 99999)}",
            "officer_name": _pick(OFFICER_NAMES),
            "officer_staff_id": f"PERF-{random.randint(100, 999)}",
            "authorising_officer": _pick(OFFICER_NAMES),
            "map_label": f"{_pick(MAP_LABELS)}-{random.randint(1, 500)}",
            "os_type": _pick(OS_TYPES),
            "status": "Open",
            "language_code": language_code,
            "review_date": review_date,
            "device": device_id,
            "addresses": [
                {
                    "target_type": "user",
                    "label": "user Address",
                    "address_line1": f"{random.randint(1, 240)} {_pick(STREETS)}",
                    "city": _pick(TOWNS),
                    "postcode": _random_postcode(),
                }
            ],
        }
        if organisation_id is not None:
            payload["organisation_id"] = organisation_id
        return payload

    def _safe_get_json(self, client, method: str, path: str, run: Run | None):
        start = perf_counter()
        response = client.request(method, path)
        elapsed_ms = (perf_counter() - start) * 1000.0
        if run is not None:
            self._record_api_metric(run, elapsed_ms, response.status_code >= 400)
        if response.status_code >= 400:
            return None
        try:
            return response.json()
        except Exception:
            return None

    def _process_provisioning_queue(self, db, run: Run) -> None:
        now = datetime.utcnow()
        queued = (
            db.execute(
                select(RunCase)
                .where(RunCase.run_id == run.id)
                .where(RunCase.state.in_(RUN_CASE_PROVISION_QUEUE_STATES))
                .where((RunCase.next_provision_at.is_(None)) | (RunCase.next_provision_at <= now))
                .order_by(RunCase.id.asc())
                .limit(self.batch_size)
            )
            .scalars()
            .all()
        )
        if not queued:
            return

        environment = db.get(Environment, run.environment_id)
        if environment is None:
            for case in queued:
                self._mark_provision_failed(case, "Environment missing", run, db)
            return

        try:
            context_data = self._get_environment_context(db, environment)
        except EnvironmentAuthChallengeError as exc:
            run.status = "action_required"
            run.blocked_reason = "env_2fa_required"
            for case in queued:
                case.state = "provision_failed"
                case.last_error = str(exc)
                case.next_provision_at = now + timedelta(minutes=5)
            return
        except EnvironmentAuthFailedError as exc:
            run.status = "action_required"
            run.blocked_reason = "env_auth_failed"
            for case in queued:
                self._mark_provision_failed(case, str(exc), run, db)
            return

        for case in queued:
            self._provision_case(db, run, case, environment, context_data)

    def _mark_provision_failed(self, case: RunCase, message: str, run: Run, db) -> None:
        case.provision_attempts += 1
        delay_seconds = min(900, 15 * (2 ** max(0, case.provision_attempts - 1)))
        case.next_provision_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        case.state = "provision_failed"
        case.last_error = message
        db.add(
            RunEvent(
                run_id=run.id,
                run_case_id=case.id,
                environment_id=run.environment_id,
                level="error",
                event_type="provision_failed",
                message=message,
                payload=json.dumps({"attempts": case.provision_attempts, "retry_in_seconds": delay_seconds}),
            )
        )

    def _mark_provision_done(self, case: RunCase, run: Run, db) -> None:
        case.state = "active"
        case.next_provision_at = None
        case.last_error = None
        db.add(
            RunEvent(
                run_id=run.id,
                run_case_id=case.id,
                environment_id=run.environment_id,
                level="info",
                event_type="provision_done",
                message=f"Case provisioned with id {case.safe_signal_case_id}",
            )
        )

    def _provision_case(self, db, run: Run, case: RunCase, environment: Environment, context_data: dict[str, object]) -> None:
        device_id = case.device_id or _random_phone()
        org_ids = context_data.get("organisation_ids") if isinstance(context_data.get("organisation_ids"), list) else []
        default_org_id = context_data.get("default_organisation_id")
        candidate_org_ids: list[object | None] = [item for item in org_ids if item is not None]
        random.shuffle(candidate_org_ids)
        if not candidate_org_ids and default_org_id is not None:
            candidate_org_ids = [default_org_id]
        if not candidate_org_ids:
            candidate_org_ids = [None]

        try:
            with authenticated_environment_client(db, environment) as client:
                created = None
                created_json = None
                org_errors: list[str] = []
                for org_id in candidate_org_ids:
                    payload = self._build_case_payload(context_data, device_id, org_id)
                    create_start = perf_counter()
                    created = client.post("/api/cases", json=payload)
                    create_ms = (perf_counter() - create_start) * 1000.0
                    self._record_api_metric(run, create_ms, created.status_code >= 400)

                    if created.status_code == 403 and len(candidate_org_ids) > 1:
                        detail = (created.text or "").strip().replace("\n", " ")[:200]
                        org_errors.append(f"org={org_id} -> 403 {detail}")
                        continue
                    if created.status_code == 503:
                        lookup_start = perf_counter()
                        lookup = client.get(f"/api/cases?search={device_id}&limit=10")
                        lookup_ms = (perf_counter() - lookup_start) * 1000.0
                        self._record_api_metric(run, lookup_ms, lookup.status_code >= 400)
                        if lookup.status_code >= 400:
                            raise RuntimeError("case create returned 503 and lookup failed")
                        lookup_json = lookup.json()
                        items = lookup_json.get("items") if isinstance(lookup_json, dict) else None
                        matches = [item for item in items if isinstance(item, dict) and item.get("device") == device_id] if isinstance(items, list) else []
                        if not matches:
                            raise RuntimeError("case create returned 503 and no matching case found")
                        created_json = matches[0]
                        break
                    if created.status_code >= 400:
                        detail = (created.text or "").strip().replace("\n", " ")[:300]
                        raise RuntimeError(f"case creation failed ({created.status_code}) {detail}")

                    created_json = created.json()
                    break

                if created_json is None:
                    if org_errors:
                        raise RuntimeError(f"case creation forbidden for accessible org candidates: {'; '.join(org_errors)}")
                    raise RuntimeError("case creation failed before receiving a response")

                case_id = None
                activation_code = None
                case_reference = None
                if isinstance(created_json, dict):
                    case_obj = created_json.get("case") if isinstance(created_json.get("case"), dict) else created_json
                    case_id = case_obj.get("id") if isinstance(case_obj, dict) else None
                    case_reference = case_obj.get("local_reference") if isinstance(case_obj, dict) else None
                    activation_code = created_json.get("activation_code") or (case_obj.get("activation_code") if isinstance(case_obj, dict) else None)
                if not case_id or not activation_code:
                    raise RuntimeError("case response missing id or activation code")

                enroll_start = perf_counter()
                enroll = client.post("/api/devices/enroll", json={"device_id": device_id, "pin": activation_code})
                enroll_ms = (perf_counter() - enroll_start) * 1000.0
                self._record_api_metric(run, enroll_ms, enroll.status_code >= 400)
                if enroll.status_code >= 400:
                    detail = (enroll.text or "").strip().replace("\n", " ")[:300]
                    raise RuntimeError(f"enrollment failed ({enroll.status_code}) {detail}")
                enroll_json = enroll.json()
                api_key = enroll_json.get("api_key") if isinstance(enroll_json, dict) else None
                if not api_key:
                    raise RuntimeError("enrollment returned no api_key")

                case.safe_signal_case_id = str(case_id)
                fallback_reference = payload.get("local_reference") if isinstance(payload, dict) else None
                case.case_reference = str(case_reference or fallback_reference or "") or None
                case.device_id = device_id
                case.device_api_key = str(api_key)
                self._mark_provision_done(case, run, db)

        except EnvironmentAuthChallengeError as exc:
            run.status = "action_required"
            run.blocked_reason = "env_2fa_required"
            self._mark_provision_failed(case, str(exc), run, db)
        except EnvironmentAuthFailedError as exc:
            run.status = "action_required"
            run.blocked_reason = "env_auth_failed"
            self._mark_provision_failed(case, str(exc), run, db)
        except Exception as exc:
            self._mark_provision_failed(case, str(exc), run, db)

    def _process_teardown_queue(self, db, run: Run) -> None:
        now = datetime.utcnow()
        queued = (
            db.execute(
                select(RunCase)
                .where(RunCase.run_id == run.id)
                .where(RunCase.state.in_(RUN_CASE_TEARDOWN_QUEUE_STATES))
                .where((RunCase.next_teardown_at.is_(None)) | (RunCase.next_teardown_at <= now))
                .order_by(RunCase.id.asc())
                .limit(self.batch_size)
            )
            .scalars()
            .all()
        )
        if not queued:
            return

        environment = db.get(Environment, run.environment_id)
        if environment is None:
            for case in queued:
                self._mark_teardown_failed(case, "Environment missing", run, db)
            return

        for case in queued:
            self._teardown_case(db, run, case, environment)

    def _mark_teardown_failed(self, case: RunCase, message: str, run: Run, db) -> None:
        case.teardown_attempts += 1
        delay_seconds = min(900, 15 * (2 ** max(0, case.teardown_attempts - 1)))
        case.next_teardown_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        case.state = "teardown_failed"
        case.last_error = message
        db.add(
            RunEvent(
                run_id=run.id,
                run_case_id=case.id,
                environment_id=run.environment_id,
                level="error",
                event_type="teardown_failed",
                message=message,
                payload=json.dumps({"attempts": case.teardown_attempts, "retry_in_seconds": delay_seconds}),
            )
        )

    def _mark_teardown_done(self, case: RunCase, run: Run, db) -> None:
        case.state = "teardown_done"
        case.next_teardown_at = None
        case.last_error = None
        db.add(
            RunEvent(
                run_id=run.id,
                run_case_id=case.id,
                environment_id=run.environment_id,
                level="info",
                event_type="teardown_done",
                message="Case teardown completed",
            )
        )

    def _extract_case_status(self, payload: object) -> str:
        if not isinstance(payload, dict):
            return ""
        source = payload.get("case") if isinstance(payload.get("case"), dict) else payload
        value = source.get("status") if isinstance(source, dict) else ""
        return str(value).strip().lower() if value else ""

    def _teardown_case(self, db, run: Run, case: RunCase, environment: Environment) -> None:
        if not case.safe_signal_case_id:
            self._mark_teardown_done(case, run, db)
            return

        teardown_mode = run.profile.teardown_mode if run.profile is not None else "delete"

        try:
            with authenticated_environment_client(db, environment) as client:
                case_id = case.safe_signal_case_id
                status = ""

                response = self._request_with_metrics(run, client, "GET", f"/api/cases/{case_id}")
                if response.status_code == 404:
                    status = ""
                elif response.status_code >= 400:
                    raise RuntimeError(f"fetch case failed ({response.status_code})")
                else:
                    status = self._extract_case_status(response.json())

                if status == "open":
                    patch = self._request_with_metrics(
                        run,
                        client,
                        "PATCH",
                        f"/api/cases/{case_id}",
                        json_body={"status": "Closed", "enrollment": 0},
                    )
                    if patch.status_code >= 400 and patch.status_code != 404:
                        raise RuntimeError(f"close case failed ({patch.status_code})")
                    status = "closed"

                if status == "closed":
                    patch = self._request_with_metrics(
                        run,
                        client,
                        "PATCH",
                        f"/api/cases/{case_id}",
                        json_body={"status": "Archived", "enrollment": 0},
                    )
                    if patch.status_code >= 400 and patch.status_code != 404:
                        raise RuntimeError(f"archive case failed ({patch.status_code})")
                    status = "archived"

                if teardown_mode == "delete":
                    delete = self._request_with_metrics(run, client, "DELETE", f"/api/cases/{case_id}")
                    if delete.status_code >= 400 and delete.status_code != 404:
                        raise RuntimeError(f"delete case failed ({delete.status_code})")

                self._mark_teardown_done(case, run, db)

        except EnvironmentAuthChallengeError as exc:
            run.status = "action_required"
            run.blocked_reason = "env_2fa_required"
            case.state = "teardown_blocked_auth"
            case.last_error = str(exc)
            case.next_teardown_at = datetime.utcnow() + timedelta(minutes=5)
            db.add(
                RunEvent(
                    run_id=run.id,
                    run_case_id=case.id,
                    environment_id=run.environment_id,
                    level="warning",
                    event_type="teardown_blocked_auth",
                    message="Teardown blocked: environment 2FA challenge required",
                )
            )
        except EnvironmentAuthFailedError as exc:
            run.status = "action_required"
            run.blocked_reason = "env_auth_failed"
            self._mark_teardown_failed(case, str(exc), run, db)
        except Exception as exc:
            self._mark_teardown_failed(case, str(exc), run, db)

    def _request_with_metrics(self, run: Run, client, method: str, path: str, *, json_body: dict | None = None):
        start = perf_counter()
        response = client.request(method, path, json=json_body)
        elapsed_ms = (perf_counter() - start) * 1000.0
        self._record_api_metric(run, elapsed_ms, response.status_code >= 400)
        return response

    def _record_api_metric(self, run: Run, elapsed_ms: float, failed: bool) -> None:
        previous_count = run.api_calls_total
        new_count = previous_count + 1
        run.api_calls_total = new_count
        if failed:
            run.api_calls_failed += 1
        run.api_last_response_ms = elapsed_ms
        if previous_count <= 0:
            run.api_avg_response_ms = elapsed_ms
        else:
            run.api_avg_response_ms = ((run.api_avg_response_ms * previous_count) + elapsed_ms) / new_count
