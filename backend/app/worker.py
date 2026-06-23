from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import httpx
import json
import math
import mimetypes
from pathlib import Path
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
RUN_CASE_ALLOCATED_STATES = {"provisioning", "provision_failed", "active", "active_alert"}
RUN_CASE_ACTIVE_STATES = {"active", "active_alert"}
RUN_CASE_TEARDOWN_QUEUE_STATES = {"teardown_pending", "teardown_failed", "teardown_blocked_auth", "scale_down_pending"}
RUN_CASE_PROVISION_QUEUE_STATES = {"provisioning", "provision_failed"}
RUN_CASE_UPDATE_STATES = {"active", "active_alert"}

RISK_LEVELS = ["High", "Medium", "Low"]
OS_TYPES = ["Android", "Apple"]
OFFICER_NAMES = ["Sergeant Hynes", "DS Murray", "Inspector Stratton", "PC Avery", "Lieutenant Fisher", "Supt. Blake"]
MAP_LABELS = ["PerfSim", "SafeSignal", "Control", "OpsBeat"]
FEMALE_NAMES = ["Aisling", "Ciara", "Fiona", "Maeve", "Niamh", "Aoife", "Saoirse", "Maya", "Ariana", "Leah"]
MALE_NAMES = ["Connor", "Liam", "Sean", "Eoin", "Patrick", "Declan", "Finn", "Noah", "Leo", "Ethan"]
LAST_NAMES = ["Murphy", "Kelly", "Byrne", "O'Neill", "Doyle", "Reilly", "Lynch", "Khan", "Singh", "Taylor"]
STREETS = ["Harper Lane", "Marlow Road", "Beacon Crescent", "Harrow Way", "Larkspur Drive"]
TOWNS = ["Belfast", "Galway", "Cork", "Limerick", "Brighton", "Slough", "Cardiff"]
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".jfif"}

VEHICLE_CATALOG: dict[str, list[str]] = {
    "Toyota": ["Corolla", "Camry", "Yaris", "RAV4"],
    "Ford": ["Focus", "Fiesta", "Mondeo", "Kuga"],
    "BMW": ["320i", "X3", "118i", "520d"],
    "Audi": ["A3", "A4", "Q3", "Q5"],
    "Vauxhall": ["Astra", "Corsa", "Insignia", "Mokka"],
    "Nissan": ["Juke", "Qashqai", "Micra", "Leaf"],
}
VEHICLE_COLORS = ["Blue", "Black", "Silver", "Red", "White", "Green", "Grey", "Navy"]
LOCATION_CLUSTERS = [
    {"latitude": 51.5074, "longitude": -0.1278},
    {"latitude": 53.4808, "longitude": -2.2426},
    {"latitude": 52.4862, "longitude": -1.8904},
    {"latitude": 55.9533, "longitude": -3.1883},
    {"latitude": 53.3498, "longitude": -6.2603},
    {"latitude": 51.4545, "longitude": -2.5879},
    {"latitude": 54.5973, "longitude": -5.9301},
]


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


def _random_dob() -> str:
    age = random.randint(25, 55)
    days = random.randint(0, 364)
    value = date.today().replace(year=date.today().year - age) - timedelta(days=days)
    return value.isoformat()


def _random_vehicle_registration() -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return (
        f"{random.choice(letters)}{random.choice(letters)}"
        f"{random.randint(0, 9)}{random.randint(0, 9)} "
        f"{random.choice(letters)}{random.choice(letters)}{random.choice(letters)}"
    )


def _extract_case_reference_from_payload(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    source = payload.get("case") if isinstance(payload.get("case"), dict) else payload
    if not isinstance(source, dict):
        return None
    for key in (
        "case_reference",
        "unique_reference",
        "short_reference",
        "short_ref",
        "case_ref",
        "case_code",
        "display_reference",
        "display_id",
        "reference",
        "case_number",
        "case_no",
        "code",
        "uid",
        "slug",
        "local_reference",
    ):
        value = source.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


class SimulatorWorker:
    def __init__(self, tick_seconds: float = 2.0, batch_size: int = 25) -> None:
        self.tick_seconds = tick_seconds
        self.batch_size = batch_size
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._env_context_cache: dict[int, dict[str, object]] = {}
        self._photo_inventory: dict[str, list[Path]] = {"male": [], "female": []}
        self._photo_inventory_loaded = False

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
        self._process_status_updates(db, run)
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
            geocenters: dict[str, dict[str, float]] = {}
            for item in organisations:
                if not isinstance(item, dict) or item.get("id") is None:
                    continue
                center = self._find_coordinate_pair_deep(item)
                if center is None:
                    continue
                geocenters[str(item.get("id"))] = center
            context_data["org_geocenters"] = geocenters

        self._env_context_cache[environment.id] = context_data
        return context_data

    def _parse_coordinate(self, value: object) -> float | None:
        if isinstance(value, (int, float)):
            parsed = float(value)
            return parsed if parsed == parsed else None
        if isinstance(value, str):
            text = value.strip().replace(",", ".")
            try:
                parsed = float(text)
            except ValueError:
                return None
            return parsed if parsed == parsed else None
        return None

    def _is_valid_coordinate_pair(self, latitude: float | None, longitude: float | None) -> bool:
        if latitude is None or longitude is None:
            return False
        return -90 <= latitude <= 90 and -180 <= longitude <= 180

    def _try_read_coordinate_pair(self, source: dict[str, object]) -> dict[str, float] | None:
        lat_keys = [
            "latitude",
            "lat",
            "map_default_lat",
            "default_lat",
            "geo_center_latitude",
            "geo_centre_latitude",
            "geocenter_latitude",
            "geocentre_latitude",
            "center_latitude",
            "centre_latitude",
        ]
        lon_keys = [
            "longitude",
            "lng",
            "lon",
            "long",
            "map_default_lng",
            "default_lng",
            "map_default_lon",
            "default_lon",
            "geo_center_longitude",
            "geo_centre_longitude",
            "geocenter_longitude",
            "geocentre_longitude",
            "center_longitude",
            "centre_longitude",
        ]
        for lat_key in lat_keys:
            if lat_key not in source:
                continue
            for lon_key in lon_keys:
                if lon_key not in source:
                    continue
                lat = self._parse_coordinate(source.get(lat_key))
                lon = self._parse_coordinate(source.get(lon_key))
                if self._is_valid_coordinate_pair(lat, lon):
                    return {"latitude": float(lat), "longitude": float(lon)}
        return None

    def _find_coordinate_pair_deep(
        self,
        value: object,
        depth: int = 0,
        seen: set[int] | None = None,
    ) -> dict[str, float] | None:
        if depth > 5:
            return None
        if seen is None:
            seen = set()
        if isinstance(value, dict):
            obj_id = id(value)
            if obj_id in seen:
                return None
            seen.add(obj_id)
            direct = self._try_read_coordinate_pair(value)
            if direct is not None:
                return direct
            keys = list(value.keys())
            keys.sort(key=lambda k: 0 if any(x in str(k).lower() for x in ("geo", "center", "centre", "location")) else 1)
            for key in keys:
                found = self._find_coordinate_pair_deep(value.get(key), depth + 1, seen)
                if found is not None:
                    return found
            return None
        if isinstance(value, list):
            for item in value:
                found = self._find_coordinate_pair_deep(item, depth + 1, seen)
                if found is not None:
                    return found
        return None

    def _meters_to_degrees(self, meters: float) -> float:
        return meters / 111000.0

    def _sample_point_around(self, center: dict[str, float], max_meters: float) -> dict[str, float]:
        distance = random.random() * self._meters_to_degrees(max_meters)
        angle = random.random() * 3.141592653589793 * 2
        return {
            "latitude": center["latitude"] + (distance * math.cos(angle)),
            "longitude": center["longitude"] + (distance * math.sin(angle)),
        }

    def _select_base_location(self, context_data: dict[str, object], organisation_id: object | None) -> dict[str, float]:
        geocenters = context_data.get("org_geocenters") if isinstance(context_data.get("org_geocenters"), dict) else {}
        if organisation_id is not None:
            center = geocenters.get(str(organisation_id))
            if isinstance(center, dict) and "latitude" in center and "longitude" in center:
                return self._sample_point_around({"latitude": float(center["latitude"]), "longitude": float(center["longitude"])}, 4000)
        fallback = random.choice(LOCATION_CLUSTERS)
        return self._sample_point_around({"latitude": fallback["latitude"], "longitude": fallback["longitude"]}, 8000)

    def _load_case_runtime_state(self, run_case: RunCase) -> dict[str, object]:
        if not run_case.schedule_overrides:
            return {}
        try:
            payload = json.loads(run_case.schedule_overrides)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_case_runtime_state(self, run_case: RunCase, state: dict[str, object]) -> None:
        run_case.schedule_overrides = json.dumps(state)

    def _random_update_interval_ms(self, run: Run) -> int:
        profile = run.profile
        if profile is None:
            return 30 * 60 * 1000
        if profile.update_max_ms <= profile.update_min_ms:
            return max(1000, profile.update_min_ms)
        return random.randint(max(1000, profile.update_min_ms), max(1000, profile.update_max_ms))

    def _random_addresses(self, target_type: str, min_count: int = 1, max_count: int = 2) -> list[dict[str, object]]:
        count = random.randint(min_count, max_count)
        return [
            {
                "target_type": target_type,
                "label": f"{target_type} Address",
                "address_line1": f"{random.randint(1, 240)} {_pick(STREETS)}",
                "city": _pick(TOWNS),
                "postcode": _random_postcode(),
            }
            for _ in range(count)
        ]

    def _random_vehicles(self, target_type: str, min_count: int = 0, max_count: int = 2) -> list[dict[str, object]]:
        count = random.randint(min_count, max_count)
        makes = list(VEHICLE_CATALOG.keys())
        vehicles: list[dict[str, object]] = []
        for _ in range(count):
            make = random.choice(makes)
            vehicles.append(
                {
                    "target_type": target_type,
                    "make": make,
                    "model": random.choice(VEHICLE_CATALOG[make]),
                    "color": random.choice(VEHICLE_COLORS),
                    "vrm": _random_vehicle_registration(),
                }
            )
        return vehicles

    def _ensure_photo_inventory(self) -> None:
        if self._photo_inventory_loaded:
            return
        root = Path(__file__).resolve().parents[2] / "simulator" / "casephotos"
        for key in ("male", "female"):
            folder = root / key
            if not folder.exists():
                self._photo_inventory[key] = []
                continue
            photos = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in PHOTO_EXTENSIONS]
            self._photo_inventory[key] = photos
        self._photo_inventory_loaded = True

    def _random_case_photo_for_gender(self, gender: str) -> Path | None:
        self._ensure_photo_inventory()
        key = "male" if str(gender).lower() == "male" else "female"
        pool = self._photo_inventory.get(key, [])
        if not pool:
            return None
        return random.choice(pool)

    def _guess_content_type(self, path: Path) -> str:
        guessed, _ = mimetypes.guess_type(str(path))
        return guessed or "application/octet-stream"

    def _build_case_payload(
        self,
        context_data: dict[str, object],
        device_id: str,
        organisation_id: object | None,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
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
            "risk_category_ids": random.sample([1, 2, 3, 4, 5], random.randint(1, 3)),
            "disability_ids": random.sample([1, 2, 3, 4], random.randint(0, 2)),
            "warning_marker_ids": random.sample([1, 2, 3, 4, 5, 6], random.randint(1, 3)),
            "device": device_id,
            "addresses": self._random_addresses("user", 1, 2),
            "vehicles": self._random_vehicles("user", 1, 3),
        }

        staged_photos: list[dict[str, object]] = []
        subject_photo = self._random_case_photo_for_gender(gender)
        if subject_photo is not None:
            staged_photos.append({"path": subject_photo, "target_type": "user", "label": f"Subject {registered_user}"})

        if random.random() < 0.35:
            perp_gender = _pick(genders if genders else ["Female", "Male"])
            perp_name = f"{_pick(FEMALE_NAMES if perp_gender.lower() == 'female' else MALE_NAMES)} {_pick(LAST_NAMES)}"
            payload["perp_name"] = perp_name
            payload["perp_gender"] = perp_gender
            payload["perp_dob"] = _random_dob()
            payload["perp_pnc_id"] = f"PNC-{random.randint(100000, 999999)}"
            payload["perp_court_order"] = f"Bail Order {random.randint(100, 999)}"
            payload["addresses"].extend(self._random_addresses("perp", 1, 2))
            payload["vehicles"].extend(self._random_vehicles("perp", 1, 2))
            perp_photo = self._random_case_photo_for_gender(perp_gender)
            if perp_photo is not None:
                staged_photos.append({"path": perp_photo, "target_type": "perp", "label": f"Perpetrator {perp_name}"})

        if organisation_id is not None:
            payload["organisation_id"] = organisation_id
        return payload, staged_photos

    def _upload_case_photos_best_effort(
        self,
        db,
        run: Run,
        case: RunCase,
        client,
        case_id: object,
        staged_photos: list[dict[str, object]],
    ) -> None:
        for photo in staged_photos:
            path = photo.get("path") if isinstance(photo, dict) else None
            if not isinstance(path, Path) or not path.exists():
                continue
            target_type = str(photo.get("target_type", "user"))
            label = str(photo.get("label", "Case Photo"))
            try:
                with path.open("rb") as handle:
                    files = {"file": (path.name, handle, self._guess_content_type(path))}
                    data = {"target_type": target_type, "label": label}
                    response = self._request_with_metrics(run, client, "POST", f"/api/cases/{case_id}/photos", data=data, files=files)
                if response.status_code >= 400:
                    db.add(
                        RunEvent(
                            run_id=run.id,
                            run_case_id=case.id,
                            environment_id=run.environment_id,
                            level="warning",
                            event_type="photo_upload_failed",
                            message=f"Photo upload failed ({response.status_code}) for {target_type}",
                            payload=(response.text or "")[:300],
                        )
                    )
            except Exception as exc:
                db.add(
                    RunEvent(
                        run_id=run.id,
                        run_case_id=case.id,
                        environment_id=run.environment_id,
                        level="warning",
                        event_type="photo_upload_failed",
                        message=f"Photo upload exception for {target_type}: {exc}",
                    )
                )

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
                staged_photos: list[dict[str, object]] = []
                selected_org_id: object | None = None
                for org_id in candidate_org_ids:
                    payload, staged_photos = self._build_case_payload(context_data, device_id, org_id)
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
                        selected_org_id = org_id
                        break
                    if created.status_code >= 400:
                        detail = (created.text or "").strip().replace("\n", " ")[:300]
                        raise RuntimeError(f"case creation failed ({created.status_code}) {detail}")

                    created_json = created.json()
                    selected_org_id = org_id
                    break

                if created_json is None:
                    if org_errors:
                        raise RuntimeError(f"case creation forbidden for accessible org candidates: {'; '.join(org_errors)}")
                    raise RuntimeError("case creation failed before receiving a response")

                case_id = None
                activation_code = None
                case_reference = _extract_case_reference_from_payload(created_json)
                if isinstance(created_json, dict):
                    case_obj = created_json.get("case") if isinstance(created_json.get("case"), dict) else created_json
                    case_id = case_obj.get("id") if isinstance(case_obj, dict) else None
                    activation_code = created_json.get("activation_code") or (case_obj.get("activation_code") if isinstance(case_obj, dict) else None)
                if not case_id or not activation_code:
                    raise RuntimeError("case response missing id or activation code")

                if not case_reference:
                    details = self._request_with_metrics(run, client, "GET", f"/api/cases/{case_id}")
                    if details.status_code < 400:
                        case_reference = _extract_case_reference_from_payload(details.json())

                self._upload_case_photos_best_effort(db, run, case, client, case_id, staged_photos)

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
                if case_reference and case_reference.lower().startswith("perf-"):
                    case_reference = None
                case.case_reference = str(case_reference or "") or None
                case.device_id = device_id
                case.device_api_key = str(api_key)
                base_location = self._select_base_location(context_data, selected_org_id)
                runtime_state = {
                    "base_lat": base_location["latitude"],
                    "base_lon": base_location["longitude"],
                    "lat": base_location["latitude"],
                    "lon": base_location["longitude"],
                    "updates": 0,
                    "active_burst_end": None,
                    "organisation_id": selected_org_id,
                }
                self._save_case_runtime_state(case, runtime_state)
                case.next_update_at = datetime.utcnow() + timedelta(milliseconds=self._random_update_interval_ms(run))
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

    def _process_status_updates(self, db, run: Run) -> None:
        if run.status != "running":
            return
        now = datetime.utcnow()
        queued = (
            db.execute(
                select(RunCase)
                .where(RunCase.run_id == run.id)
                .where(RunCase.state.in_(RUN_CASE_UPDATE_STATES))
                .where((RunCase.next_update_at.is_(None)) | (RunCase.next_update_at <= now))
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
            return

        with httpx.Client(base_url=environment.base_url.rstrip("/"), timeout=20, follow_redirects=True) as client:
            for case in queued:
                self._send_status_update(db, run, case, client)

    def _send_status_update(self, db, run: Run, case: RunCase, client) -> None:
        now = datetime.utcnow()
        runtime = self._load_case_runtime_state(case)
        lat = float(runtime.get("lat", 0) or 0)
        lon = float(runtime.get("lon", 0) or 0)
        base_lat = float(runtime.get("base_lat", lat) or lat)
        base_lon = float(runtime.get("base_lon", lon) or lon)
        updates = int(runtime.get("updates", 0) or 0)
        active_burst_end = runtime.get("active_burst_end")

        profile = run.profile
        if profile is None:
            activation_chance = 0.03
            active_interval_ms = 30_000
            active_duration_ms = 15 * 60_000
        else:
            activation_chance = max(0.0, min(1.0, float(profile.activation_chance)))
            active_interval_ms = max(1000, int(profile.active_interval_ms))
            active_duration_ms = max(1000, int(profile.active_duration_ms))

        is_active = False
        if isinstance(active_burst_end, str):
            try:
                is_active = datetime.fromisoformat(active_burst_end) > now
            except ValueError:
                is_active = False

        if not is_active and random.random() < activation_chance:
            is_active = True
            active_burst_end = (now + timedelta(milliseconds=active_duration_ms)).isoformat()

        step_meters = 50 if is_active else 250
        moved = self._sample_point_around({"latitude": base_lat, "longitude": base_lon}, step_meters)
        lat = moved["latitude"]
        lon = moved["longitude"]

        if not case.device_id or not case.device_api_key:
            case.last_error = "Missing device credentials for status update"
            case.next_update_at = now + timedelta(seconds=30)
            return

        payload = {
            "device_id": case.device_id,
            "api_key": case.device_api_key,
            "latitude": lat,
            "longitude": lon,
            "battery": max(5, 100 - (updates % 100)),
            "speed": 12 if is_active else 3,
            "heading": random.random() * 360,
            "activation": 1 if is_active else 0,
        }

        try:
            response = self._request_with_metrics(run, client, "POST", "/api/devices/statusupdate", json_body=payload)
            if response.status_code >= 400:
                detail = (response.text or "").strip().replace("\n", " ")[:260]
                case.last_error = f"status update failed ({response.status_code}) {detail}"
                db.add(
                    RunEvent(
                        run_id=run.id,
                        run_case_id=case.id,
                        environment_id=run.environment_id,
                        level="warning",
                        event_type="status_update_failed",
                        message=case.last_error,
                    )
                )
                case.next_update_at = now + timedelta(seconds=15)
                return

            updates += 1
            case.last_update_at = now
            case.last_error = None
            case.state = "active_alert" if is_active else "active"
            next_ms = active_interval_ms if is_active else self._random_update_interval_ms(run)
            case.next_update_at = now + timedelta(milliseconds=next_ms)
            runtime.update(
                {
                    "lat": lat,
                    "lon": lon,
                    "base_lat": lat,
                    "base_lon": lon,
                    "updates": updates,
                    "active_burst_end": active_burst_end,
                }
            )
            self._save_case_runtime_state(case, runtime)
        except Exception as exc:
            case.last_error = f"status update exception: {exc}"
            case.next_update_at = now + timedelta(seconds=20)
            db.add(
                RunEvent(
                    run_id=run.id,
                    run_case_id=case.id,
                    environment_id=run.environment_id,
                    level="warning",
                    event_type="status_update_failed",
                    message=case.last_error,
                )
            )

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

    def _request_with_metrics(
        self,
        run: Run,
        client,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        data: dict[str, str] | None = None,
        files=None,
    ):
        start = perf_counter()
        response = client.request(method, path, json=json_body, data=data, files=files)
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
