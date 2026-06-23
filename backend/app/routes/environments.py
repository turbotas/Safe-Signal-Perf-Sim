from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Environment, EnvironmentAuthSession, Run, User
from app.schemas import (
    Environment2FASubmitRequest,
    EnvironmentAuthTestResponse,
    EnvironmentCreate,
    EnvironmentOut,
    EnvironmentUpdate,
)
from app.security import decrypt_secret, encrypt_secret
from app.services.safe_signal_auth import attempt_safe_signal_login

router = APIRouter(prefix="/api/sim/environments", tags=["environments"])


def to_environment_out(model: Environment) -> EnvironmentOut:
    latest_session = None
    if model.auth_sessions:
        latest_session = max(model.auth_sessions, key=lambda item: item.id)
    return EnvironmentOut(
        id=model.id,
        name=model.name,
        base_url=model.base_url,
        api_username=model.api_username,
        auth_mode=model.auth_mode,
        is_active=model.is_active,
        credential_version=model.credential_version,
        has_password=bool(model.encrypted_api_password),
        last_auth_ok_at=model.last_auth_ok_at,
        last_auth_error=model.last_auth_error,
        auth_session_state=latest_session.state if latest_session else None,
        auth_session_expires_at=latest_session.expires_at if latest_session else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def get_or_create_auth_session(db: Session, environment_id: int) -> EnvironmentAuthSession:
    row = db.execute(
        select(EnvironmentAuthSession)
        .where(EnvironmentAuthSession.environment_id == environment_id)
        .order_by(EnvironmentAuthSession.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = EnvironmentAuthSession(environment_id=environment_id, state="failed")
    db.add(row)
    db.flush()
    return row


def apply_auth_result(
    env: Environment,
    session: EnvironmentAuthSession,
    auth_result: dict[str, object],
    *,
    code_submitted: bool,
) -> EnvironmentAuthTestResponse:
    now = datetime.utcnow()
    session.last_attempt_at = now
    status_value = str(auth_result.get("status", "failed"))
    message = str(auth_result.get("message", "Authentication failed"))

    if status_value == "success":
        session.state = "valid"
        session.challenge_type = None
        session.challenge_context = None
        session.last_success_at = now
        session.expires_at = now + timedelta(hours=settings.env_session_hours)
        blob = str(auth_result.get("session_blob", ""))
        session.encrypted_session_blob = encrypt_secret(blob) if blob else None
        env.last_auth_ok_at = now
        env.last_auth_error = None
        return EnvironmentAuthTestResponse(status="success", message=message, challenge_required=False)

    if status_value == "challenge_required":
        session.state = "challenge_required"
        session.challenge_type = str(auth_result.get("challenge_type", "otp"))
        session.challenge_context = str(auth_result.get("challenge_context", ""))
        session.expires_at = None
        env.last_auth_error = "2FA challenge required"
        blocked_message = "2FA code required to complete authentication"
        if code_submitted:
            blocked_message = "2FA code rejected or expired"
        return EnvironmentAuthTestResponse(
            status="challenge_required",
            message=blocked_message,
            challenge_type=session.challenge_type,
            challenge_required=True,
        )

    session.state = "failed"
    session.challenge_type = None
    session.challenge_context = None
    session.expires_at = None
    detail = str(auth_result.get("detail", "")).strip()
    env.last_auth_error = message if not detail else f"{message}: {detail}"
    return EnvironmentAuthTestResponse(status="failed", message=env.last_auth_error, challenge_required=False)


@router.get("", response_model=list[EnvironmentOut])
def list_environments(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[EnvironmentOut]:
    rows = db.execute(select(Environment).order_by(Environment.name.asc())).scalars().all()
    return [to_environment_out(row) for row in rows]


@router.post("", response_model=EnvironmentOut, status_code=status.HTTP_201_CREATED)
def create_environment(
    payload: EnvironmentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EnvironmentOut:
    existing = db.execute(select(Environment).where(Environment.name == payload.name.strip())).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Environment name already exists")

    row = Environment(
        name=payload.name.strip(),
        base_url=payload.base_url.strip().rstrip("/"),
        api_username=payload.api_username.strip(),
        encrypted_api_password=encrypt_secret(payload.api_password),
        auth_mode=payload.auth_mode,
        is_active=payload.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return to_environment_out(row)


@router.get("/{environment_id}", response_model=EnvironmentOut)
def get_environment(environment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> EnvironmentOut:
    row = db.get(Environment, environment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    return to_environment_out(row)


@router.patch("/{environment_id}", response_model=EnvironmentOut)
def update_environment(
    environment_id: int,
    payload: EnvironmentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EnvironmentOut:
    row = db.get(Environment, environment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"]:
        new_name = updates["name"].strip()
        existing = db.execute(select(Environment).where(Environment.name == new_name, Environment.id != row.id)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Environment name already exists")
        row.name = new_name
    if "base_url" in updates and updates["base_url"]:
        row.base_url = updates["base_url"].strip().rstrip("/")
    if "api_username" in updates and updates["api_username"]:
        row.api_username = updates["api_username"].strip()
    if "auth_mode" in updates and updates["auth_mode"]:
        row.auth_mode = updates["auth_mode"]
    if "is_active" in updates:
        row.is_active = bool(updates["is_active"])
    if "api_password" in updates and updates["api_password"]:
        row.encrypted_api_password = encrypt_secret(updates["api_password"])
        row.credential_version += 1

    db.commit()
    db.refresh(row)
    return to_environment_out(row)


@router.post("/{environment_id}/test-auth", response_model=EnvironmentAuthTestResponse)
def test_environment_auth(
    environment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EnvironmentAuthTestResponse:
    env = db.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")

    password = decrypt_secret(env.encrypted_api_password)
    auth_result = attempt_safe_signal_login(
        base_url=env.base_url,
        username=env.api_username,
        password=password,
    )
    session = get_or_create_auth_session(db, env.id)
    result = apply_auth_result(env, session, auth_result, code_submitted=False)
    db.commit()
    return result


@router.post("/{environment_id}/2fa/submit", response_model=EnvironmentAuthTestResponse)
def submit_environment_2fa(
    environment_id: int,
    payload: Environment2FASubmitRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EnvironmentAuthTestResponse:
    env = db.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")

    password = decrypt_secret(env.encrypted_api_password)
    auth_result = attempt_safe_signal_login(
        base_url=env.base_url,
        username=env.api_username,
        password=password,
        code=payload.code.strip(),
    )
    session = get_or_create_auth_session(db, env.id)
    result = apply_auth_result(env, session, auth_result, code_submitted=True)
    db.commit()
    return result


@router.delete("/{environment_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_environment(
    environment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    env = db.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")

    linked_run = db.execute(select(Run.id).where(Run.environment_id == env.id).limit(1)).scalar_one_or_none()
    if linked_run is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Environment is used by an existing run")

    db.delete(env)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
