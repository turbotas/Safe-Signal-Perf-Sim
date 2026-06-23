from __future__ import annotations

from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+$")


class HealthResponse(BaseModel):
    status: str = "ok"


class ApiInfoResponse(BaseModel):
    service: str
    status: str
    docs_url: str
    health_url: str
    console_url: str


class UserBase(BaseModel):
    email: str
    is_active: bool = True
    is_admin: bool = False

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.match(normalized):
            raise ValueError("email must look like user@domain")
        return normalized


class UserCreate(UserBase):
    password: str = Field(min_length=10, max_length=128)


class UserUpdate(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class UserPasswordReset(BaseModel):
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.match(normalized):
            raise ValueError("email must look like user@domain")
        return normalized


class AuthMeResponse(BaseModel):
    user: UserOut


class EnvironmentBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    base_url: str = Field(min_length=3, max_length=500)
    api_username: str = Field(min_length=1, max_length=255)
    auth_mode: str = Field(default="auto_detect", max_length=40)
    is_active: bool = True


class EnvironmentCreate(EnvironmentBase):
    api_password: str = Field(min_length=1, max_length=255)


class EnvironmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    base_url: str | None = Field(default=None, min_length=3, max_length=500)
    api_username: str | None = Field(default=None, min_length=1, max_length=255)
    api_password: str | None = Field(default=None, max_length=255)
    auth_mode: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None


class EnvironmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_url: str
    api_username: str
    auth_mode: str
    is_active: bool
    credential_version: int
    has_password: bool
    last_auth_ok_at: datetime | None = None
    last_auth_error: str | None = None
    auth_session_state: str | None = None
    auth_session_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EnvironmentAuthTestResponse(BaseModel):
    status: str
    message: str
    challenge_type: str | None = None
    challenge_required: bool = False


class Environment2FASubmitRequest(BaseModel):
    code: str = Field(min_length=3, max_length=20)


class RunProfileBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    device_count_initial: int = Field(default=200, ge=1, le=10000)
    update_min_ms: int = Field(default=30 * 60 * 1000, ge=1000)
    update_max_ms: int = Field(default=60 * 60 * 1000, ge=1000)
    activation_chance: float = Field(default=0.03, ge=0.0, le=1.0)
    active_interval_ms: int = Field(default=30 * 1000, ge=1000)
    active_duration_ms: int = Field(default=15 * 60 * 1000, ge=1000)
    case_creation_delay_ms: int = Field(default=0, ge=0, le=10000)
    teardown_mode: str = Field(default="delete", pattern="^(delete|archive)$")

    @field_validator("update_max_ms")
    @classmethod
    def validate_update_range(cls, value: int, info):
        min_value = info.data.get("update_min_ms", value)
        if value < min_value:
            raise ValueError("update_max_ms must be greater than or equal to update_min_ms")
        return value


class RunProfileCreate(RunProfileBase):
    pass


class RunProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    device_count_initial: int | None = Field(default=None, ge=1, le=10000)
    update_min_ms: int | None = Field(default=None, ge=1000)
    update_max_ms: int | None = Field(default=None, ge=1000)
    activation_chance: float | None = Field(default=None, ge=0.0, le=1.0)
    active_interval_ms: int | None = Field(default=None, ge=1000)
    active_duration_ms: int | None = Field(default=None, ge=1000)
    case_creation_delay_ms: int | None = Field(default=None, ge=0, le=10000)
    teardown_mode: str | None = Field(default=None, pattern="^(delete|archive)$")


class RunProfileOut(RunProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    environment_id: int
    profile_id: int | None = None
    desired_case_count: int | None = Field(default=None, ge=1, le=10000)


class RunScaleRequest(BaseModel):
    delta_cases: int = Field(ge=-10000, le=10000)

    @field_validator("delta_cases")
    @classmethod
    def non_zero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta_cases must not be zero")
        return value


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    environment_id: int
    profile_id: int | None
    status: str
    blocked_reason: str | None
    desired_case_count: int
    active_case_count: int
    api_calls_total: int
    api_calls_failed: int
    api_avg_response_ms: float
    api_last_response_ms: float
    created_by_user_id: int
    started_at: datetime | None
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RunEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    run_case_id: int | None
    environment_id: int
    level: str
    event_type: str
    message: str
    payload: str | None
    created_at: datetime


class RunCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    environment_id: int
    safe_signal_case_id: str | None
    case_reference: str | None
    device_id: str | None
    state: str
    next_update_at: datetime | None
    last_update_at: datetime | None
    provision_attempts: int
    next_provision_at: datetime | None
    teardown_attempts: int
    next_teardown_at: datetime | None
    last_error: str | None
    schedule_overrides: str | None
    created_at: datetime
    updated_at: datetime
