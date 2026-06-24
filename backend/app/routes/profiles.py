from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Run, RunProfile, User
from app.schemas import RunProfileCreate, RunProfileOut, RunProfileUpdate

router = APIRouter(prefix="/api/sim/profiles", tags=["profiles"])


@router.get("", response_model=list[RunProfileOut])
def list_profiles(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[RunProfileOut]:
    rows = db.execute(select(RunProfile).order_by(RunProfile.name.asc())).scalars().all()
    return list(rows)


@router.post("", response_model=RunProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: RunProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunProfileOut:
    existing = db.execute(select(RunProfile).where(RunProfile.name == payload.name.strip())).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile name already exists")

    row = RunProfile(
        name=payload.name.strip(),
        profile_kind=payload.profile_kind,
        device_count_initial=payload.device_count_initial,
        update_min_ms=payload.update_min_ms,
        update_max_ms=payload.update_max_ms,
        activation_chance=payload.activation_chance,
        active_interval_ms=payload.active_interval_ms,
        active_duration_ms=payload.active_duration_ms,
        case_creation_delay_ms=payload.case_creation_delay_ms,
        teardown_mode=payload.teardown_mode,
        caseworker_worker_count_initial=payload.caseworker_worker_count_initial,
        caseworker_actions_per_min_per_worker=payload.caseworker_actions_per_min_per_worker,
        caseworker_think_time_min_ms=payload.caseworker_think_time_min_ms,
        caseworker_think_time_max_ms=payload.caseworker_think_time_max_ms,
        caseworker_read_ratio=payload.caseworker_read_ratio,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{profile_id}", response_model=RunProfileOut)
def update_profile(
    profile_id: int,
    payload: RunProfileUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> RunProfileOut:
    row = db.get(RunProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"]:
        new_name = updates["name"].strip()
        existing = db.execute(select(RunProfile).where(RunProfile.name == new_name, RunProfile.id != row.id)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile name already exists")
        row.name = new_name

    for key in (
        "profile_kind",
        "device_count_initial",
        "update_min_ms",
        "update_max_ms",
        "activation_chance",
        "active_interval_ms",
        "active_duration_ms",
        "case_creation_delay_ms",
        "teardown_mode",
        "caseworker_worker_count_initial",
        "caseworker_actions_per_min_per_worker",
        "caseworker_think_time_min_ms",
        "caseworker_think_time_max_ms",
        "caseworker_read_ratio",
    ):
        if key in updates:
            setattr(row, key, updates[key])

    if row.update_max_ms < row.update_min_ms:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="update_max_ms must be >= update_min_ms")
    if row.caseworker_think_time_max_ms < row.caseworker_think_time_min_ms:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="caseworker_think_time_max_ms must be >= caseworker_think_time_min_ms",
        )

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_profile(profile_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Response:
    row = db.get(RunProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    linked_run = db.execute(select(Run.id).where(Run.profile_id == row.id).limit(1)).scalar_one_or_none()
    if linked_run is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile is used by an existing run")

    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
