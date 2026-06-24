from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.routes.auth import router as auth_router
from app.routes.environments import router as environments_router
from app.routes.profiles import router as profiles_router
from app.routes.runs import router as runs_router
from app.routes.users import router as users_router
from app.schemas import ApiInfoResponse, HealthResponse
from app.security import hash_password
from app.worker import SimulatorWorker


worker = SimulatorWorker()


def seed_admin_if_missing() -> None:
    with SessionLocal() as db:
        existing = db.execute(select(User).limit(1)).scalar_one_or_none()
        if existing is not None:
            return
        admin = User(
            email=settings.seed_admin_email.lower().strip(),
            password_hash=hash_password(settings.seed_admin_password),
            is_active=True,
            is_admin=True,
        )
        db.add(admin)
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    path = settings.sqlite_path
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        seed_admin_if_missing()
    except OperationalError:
        # Database likely not migrated yet. Startup still allowed for health checks.
        pass
    if settings.worker_timing_debug:
        logging.getLogger("app.worker").setLevel(logging.INFO)
    worker.start()
    yield
    await worker.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/console", StaticFiles(directory=str(static_dir), html=True), name="console")
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(environments_router)
app.include_router(profiles_router)
app.include_router(runs_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/", response_model=ApiInfoResponse, tags=["health"])
def api_info() -> ApiInfoResponse:
    return ApiInfoResponse(
        service=settings.app_name,
        status="running",
        docs_url="/docs",
        health_url="/health",
        console_url="/console",
    )
