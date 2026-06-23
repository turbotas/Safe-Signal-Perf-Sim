from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Environment, EnvironmentAuthSession
from app.security import decrypt_secret, encrypt_secret
from app.services.safe_signal_auth import attempt_safe_signal_login


class EnvironmentAuthChallengeError(RuntimeError):
    pass


class EnvironmentAuthFailedError(RuntimeError):
    pass


def _latest_auth_session(db: Session, environment_id: int) -> EnvironmentAuthSession | None:
    return db.execute(
        select(EnvironmentAuthSession)
        .where(EnvironmentAuthSession.environment_id == environment_id)
        .order_by(EnvironmentAuthSession.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _get_or_create_auth_session(db: Session, environment_id: int) -> EnvironmentAuthSession:
    row = _latest_auth_session(db, environment_id)
    if row is not None:
        return row
    row = EnvironmentAuthSession(environment_id=environment_id, state="failed")
    db.add(row)
    db.flush()
    return row


def _load_cookies_from_session_blob(blob: str | None) -> dict[str, str]:
    if not blob:
        return {}
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        return {}
    cookies = payload.get("cookies") if isinstance(payload, dict) else None
    return cookies if isinstance(cookies, dict) else {}


def _refresh_login(db: Session, environment: Environment, *, code: str | None = None) -> EnvironmentAuthSession:
    session = _get_or_create_auth_session(db, environment.id)
    password = decrypt_secret(environment.encrypted_api_password)
    result = attempt_safe_signal_login(environment.base_url, environment.api_username, password, code=code)
    now = datetime.utcnow()
    session.last_attempt_at = now
    status_value = str(result.get("status", "failed"))

    if status_value == "success":
        session.state = "valid"
        session.challenge_type = None
        session.challenge_context = None
        session.last_success_at = now
        session.expires_at = now + timedelta(hours=settings.env_session_hours)
        blob = str(result.get("session_blob", ""))
        session.encrypted_session_blob = encrypt_secret(blob) if blob else None
        environment.last_auth_ok_at = now
        environment.last_auth_error = None
        return session

    if status_value == "challenge_required":
        session.state = "challenge_required"
        session.challenge_type = str(result.get("challenge_type", "otp"))
        session.challenge_context = str(result.get("challenge_context", ""))
        session.expires_at = None
        environment.last_auth_error = "2FA challenge required"
        raise EnvironmentAuthChallengeError("2FA challenge required")

    session.state = "failed"
    session.challenge_type = None
    session.challenge_context = None
    session.expires_at = None
    detail = str(result.get("detail", "")).strip()
    message = str(result.get("message", "Authentication failed")).strip()
    environment.last_auth_error = message if not detail else f"{message}: {detail}"
    raise EnvironmentAuthFailedError(environment.last_auth_error)


@contextmanager
def authenticated_environment_client(db: Session, environment: Environment):
    now = datetime.utcnow()
    session = _latest_auth_session(db, environment.id)
    cookies: dict[str, str] = {}

    if session and session.state == "valid" and session.expires_at and session.expires_at > now and session.encrypted_session_blob:
        try:
            blob = decrypt_secret(session.encrypted_session_blob)
            cookies = _load_cookies_from_session_blob(blob)
        except Exception:
            cookies = {}

    if not cookies:
        session = _refresh_login(db, environment)
        blob = decrypt_secret(session.encrypted_session_blob) if session.encrypted_session_blob else ""
        cookies = _load_cookies_from_session_blob(blob)

    base_url = environment.base_url.rstrip("/")
    with httpx.Client(base_url=base_url, timeout=settings.safe_signal_auth_timeout_seconds, follow_redirects=True) as client:
        if cookies:
            client.cookies.update(cookies)

        if cookies:
            probe = client.get("/api/auth/me")
            if probe.status_code == 401:
                refreshed = _refresh_login(db, environment)
                refreshed_blob = decrypt_secret(refreshed.encrypted_session_blob) if refreshed.encrypted_session_blob else ""
                refreshed_cookies = _load_cookies_from_session_blob(refreshed_blob)
                client.cookies.clear()
                if refreshed_cookies:
                    client.cookies.update(refreshed_cookies)

        yield client
