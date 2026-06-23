from __future__ import annotations

import json

import httpx

from app.config import settings


def _looks_like_2fa_challenge(status_code: int, body_text: str) -> bool:
    if status_code not in (400, 401, 403):
        return False
    text = body_text.lower()
    if "2fa" in text or "otp" in text or "two-factor" in text:
        return True
    if "code" in text and ("required" in text or "missing" in text or "verify" in text):
        return True
    return False


def attempt_safe_signal_login(base_url: str, username: str, password: str, code: str | None = None) -> dict[str, object]:
    login_url = f"{base_url.rstrip('/')}/api/auth/login"
    payload: dict[str, str] = {"email": username, "password": password}
    if code:
        payload["code"] = code

    try:
        with httpx.Client(timeout=settings.safe_signal_auth_timeout_seconds, follow_redirects=True) as client:
            response = client.post(login_url, json=payload)
            text = response.text or ""
            if response.status_code in (200, 204):
                cookies = dict(client.cookies.items())
                return {
                    "status": "success",
                    "message": "Authenticated against environment",
                    "session_blob": json.dumps({"cookies": cookies}),
                }
            if _looks_like_2fa_challenge(response.status_code, text):
                return {
                    "status": "challenge_required",
                    "message": "2FA challenge required",
                    "challenge_type": "otp",
                    "challenge_context": json.dumps({"hint": "Enter one-time code from authenticator"}),
                }
            return {
                "status": "failed",
                "message": f"Auth failed ({response.status_code})",
                "detail": text[:500],
            }
    except httpx.HTTPError as exc:
        return {
            "status": "failed",
            "message": "Environment auth request failed",
            "detail": str(exc),
        }
