from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_DB_PATH = (Path(__file__).resolve().parents[1] / "data" / "simulator.db").as_posix()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SIM_", extra="ignore")

    app_name: str = "Safe Signal Performance Simulator API"
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    secret_key: str = "dev-secret-change-me"
    session_cookie_name: str = "sim_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 24

    seed_admin_email: str = "admin@perfsim.local"
    seed_admin_password: str = "ChangeMeNow123!"
    safe_signal_auth_timeout_seconds: int = 15
    env_session_hours: int = 8
    worker_timing_debug: bool = False
    worker_timing_sample_rate: float = 0.1
    worker_timing_slow_ms: float = 2000.0

    @property
    def normalized_secret_key(self) -> str:
        digest = hashlib.sha256(self.secret_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii")

    @property
    def sqlite_path(self) -> Path | None:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        raw = self.database_url[len(prefix) :]
        return Path(raw)


settings = Settings()
