from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    sessions: Mapped[list[UserSession]] = relationship(back_populates="user", cascade="all, delete-orphan")
    run_profiles: Mapped[list[RunProfile]] = relationship(back_populates="created_by")
    runs: Mapped[list[Run]] = relationship(back_populates="created_by")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class Environment(TimestampMixin, Base):
    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_api_password: Mapped[str] = mapped_column(Text, nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(40), default="auto_detect", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_auth_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_auth_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    auth_sessions: Mapped[list[EnvironmentAuthSession]] = relationship(
        back_populates="environment", cascade="all, delete-orphan"
    )
    runs: Mapped[list[Run]] = relationship(back_populates="environment")


class EnvironmentAuthSession(Base):
    __tablename__ = "environment_auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="failed")
    encrypted_session_blob: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    challenge_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    challenge_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    environment: Mapped[Environment] = relationship(back_populates="auth_sessions")


class RunProfile(TimestampMixin, Base):
    __tablename__ = "run_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    device_count_initial: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    update_min_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=30 * 60 * 1000)
    update_max_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=60 * 60 * 1000)
    activation_chance: Mapped[float] = mapped_column(Float, nullable=False, default=0.03)
    active_interval_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=30 * 1000)
    active_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=15 * 60 * 1000)
    case_creation_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    teardown_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="delete")
    profile_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="device_telemetry")
    caseworker_worker_count_initial: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    caseworker_actions_per_min_per_worker: Mapped[float] = mapped_column(Float, nullable=False, default=6.0)
    caseworker_think_time_min_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1500)
    caseworker_think_time_max_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=6000)
    caseworker_read_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    created_by: Mapped[User] = relationship(back_populates="run_profiles")
    runs: Mapped[list[Run]] = relationship(back_populates="profile")


class Run(TimestampMixin, Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="RESTRICT"), nullable=False, index=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("run_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id", ondelete="RESTRICT"), nullable=True, index=True)
    run_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="device_telemetry")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="starting")
    blocked_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    desired_case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actions_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actions_failed_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actions_per_second_current: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    actions_per_second_avg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    api_calls_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_calls_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_avg_response_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    api_last_response_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    environment: Mapped[Environment] = relationship(back_populates="runs")
    profile: Mapped[RunProfile | None] = relationship(back_populates="runs")
    created_by: Mapped[User] = relationship(back_populates="runs")
    cases: Mapped[list[RunCase]] = relationship(back_populates="run", cascade="all, delete-orphan")
    events: Mapped[list[RunEvent]] = relationship(back_populates="run", cascade="all, delete-orphan")
    action_stats: Mapped[list[RunActionStat]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunActionStat(TimestampMixin, Base):
    __tablename__ = "run_action_stats"
    __table_args__ = (UniqueConstraint("run_id", "action_type", name="uq_run_action_stats_run_action_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="RESTRICT"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_response_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_response_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    run: Mapped[Run] = relationship(back_populates="action_stats")


class RunCase(TimestampMixin, Base):
    __tablename__ = "run_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="RESTRICT"), nullable=False, index=True)
    safe_signal_case_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    case_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="provisioning")
    next_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    provision_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_provision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    teardown_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_teardown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_overrides: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[Run] = relationship(back_populates="cases")


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    run_case_id: Mapped[int | None] = mapped_column(ForeignKey("run_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="RESTRICT"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)

    run: Mapped[Run] = relationship(back_populates="events")
