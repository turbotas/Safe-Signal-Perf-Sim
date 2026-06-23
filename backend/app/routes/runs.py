from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Environment, Run, RunCase, RunEvent, RunProfile, User
from app.schemas import RunCaseOut, RunCreate, RunEventOut, RunOut, RunScaleRequest

router = APIRouter(prefix="/api/sim/runs", tags=["runs"])


def add_run_event(
    db: Session,
    *,
    run_id: int,
    environment_id: int,
    event_type: str,
    message: str,
    level: str = "info",
    payload: str | None = None,
) -> None:
    db.add(
        RunEvent(
            run_id=run_id,
            environment_id=environment_id,
            level=level,
            event_type=event_type,
            message=message,
            payload=payload,
        )
    )


@router.get("", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[RunOut]:
    rows = db.execute(select(Run).order_by(Run.created_at.desc())).scalars().all()
    return list(rows)


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: RunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunOut:
    env = db.get(Environment, payload.environment_id)
    if env is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    if not env.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Environment is inactive")

    profile: RunProfile | None = None
    if payload.profile_id is not None:
        profile = db.get(RunProfile, payload.profile_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    desired_case_count = payload.desired_case_count
    if desired_case_count is None:
        desired_case_count = profile.device_count_initial if profile else 200

    now = datetime.utcnow()
    run = Run(
        environment_id=env.id,
        profile_id=profile.id if profile else None,
        status="running",
        blocked_reason=None,
        desired_case_count=desired_case_count,
        active_case_count=0,
        created_by_user_id=current_user.id,
        started_at=now,
        stopped_at=None,
    )
    db.add(run)
    db.flush()
    add_run_event(
        db,
        run_id=run.id,
        environment_id=env.id,
        event_type="run_started",
        message=f"Run started with desired_case_count={desired_case_count}",
    )
    db.commit()
    db.refresh(run)
    return run


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> RunOut:
    row = db.get(Run, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return row


@router.get("/{run_id}/events", response_model=list[RunEventOut])
def list_run_events(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[RunEventOut]:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    rows = db.execute(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.created_at.desc())).scalars().all()
    return list(rows)


@router.get("/{run_id}/cases", response_model=list[RunCaseOut])
def list_run_cases(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[RunCaseOut]:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    rows = db.execute(select(RunCase).where(RunCase.run_id == run_id).order_by(RunCase.id.asc())).scalars().all()
    return list(rows)


@router.post("/{run_id}/stop", response_model=RunOut)
def stop_run(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> RunOut:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status == "stopped":
        return run

    active_states = ("active", "provisioning", "provision_failed")
    cases = db.execute(select(RunCase).where(RunCase.run_id == run.id).where(RunCase.state.in_(active_states))).scalars().all()
    for case in cases:
        case.state = "teardown_pending"
        case.next_teardown_at = datetime.utcnow()

    run.status = "stopping"
    run.desired_case_count = 0
    run.blocked_reason = None
    add_run_event(
        db,
        run_id=run.id,
        environment_id=run.environment_id,
        event_type="run_stopping",
        message=f"Run marked as stopping and queued {len(cases)} cases for teardown",
    )
    db.commit()
    db.refresh(run)
    return run


@router.post("/{run_id}/scale", response_model=RunOut)
def scale_run(
    run_id: int,
    payload: RunScaleRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> RunOut:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status not in ("running", "action_required"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run cannot be scaled in its current state")

    target = run.desired_case_count + payload.delta_cases
    if target < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="desired_case_count cannot be negative")

    run.desired_case_count = target
    add_run_event(
        db,
        run_id=run.id,
        environment_id=run.environment_id,
        event_type="run_scaled",
        message=f"Adjusted desired_case_count by {payload.delta_cases} to {target}",
    )
    db.commit()
    db.refresh(run)
    return run


@router.post("/{run_id}/resume", response_model=RunOut)
def resume_run(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> RunOut:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.desired_case_count <= 0:
        run.desired_case_count = run.profile.device_count_initial if run.profile is not None else 50

    if run.status == "stopped":
        run.stopped_at = None

    run.status = "running"
    run.blocked_reason = None
    add_run_event(
        db,
        run_id=run.id,
        environment_id=run.environment_id,
        event_type="run_resumed",
        message="Run resumed",
    )
    db.commit()
    db.refresh(run)
    return run


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_run(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Response:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status == "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stop the run before deleting it")

    db.delete(run)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
