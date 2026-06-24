from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Environment, Run, RunActionStat, RunCase, RunEvent, RunProfile, User
from app.schemas import RunCaseOut, RunCreate, RunEventOut, RunMetricsOut, RunOut, RunScaleRequest

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
    run_kind = "device_telemetry"
    if payload.profile_id is not None:
        profile = db.get(RunProfile, payload.profile_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        run_kind = profile.profile_kind or "device_telemetry"

    parent_run: Run | None = None
    if run_kind == "case_worker":
        if payload.parent_run_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="parent_run_id is required for case_worker runs")
        parent_run = db.get(Run, payload.parent_run_id)
        if parent_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent run not found")
        if parent_run.run_kind != "device_telemetry":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Parent run must be a telemetry run")
        if parent_run.environment_id != env.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Parent run must use the same environment")
        if parent_run.status != "running":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parent run must be running")
    elif payload.parent_run_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="parent_run_id can only be used for case_worker runs",
        )

    desired_case_count = payload.desired_case_count
    if desired_case_count is None:
        if run_kind == "case_worker":
            desired_case_count = profile.caseworker_worker_count_initial if profile else 20
        else:
            desired_case_count = profile.device_count_initial if profile else 200

    now = datetime.utcnow()
    run = Run(
        environment_id=env.id,
        profile_id=profile.id if profile else None,
        parent_run_id=parent_run.id if parent_run else None,
        run_kind=run_kind,
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


@router.get("/{run_id}/metrics", response_model=RunMetricsOut)
def get_run_metrics(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> RunMetricsOut:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    stats = (
        db.execute(select(RunActionStat).where(RunActionStat.run_id == run_id).order_by(RunActionStat.action_type.asc()))
        .scalars()
        .all()
    )
    return RunMetricsOut(
        run_id=run.id,
        run_kind=run.run_kind,
        actions_total=run.actions_total,
        actions_failed_total=run.actions_failed_total,
        actions_per_second_current=run.actions_per_second_current,
        actions_per_second_avg=run.actions_per_second_avg,
        api_calls_total=run.api_calls_total,
        api_calls_failed=run.api_calls_failed,
        api_avg_response_ms=run.api_avg_response_ms,
        api_last_response_ms=run.api_last_response_ms,
        action_stats=stats,
    )


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

    if run.run_kind == "device_telemetry":
        active_child = db.execute(
            select(Run.id)
            .where(Run.parent_run_id == run.id)
            .where(Run.run_kind == "case_worker")
            .where(Run.status.in_(("running", "starting", "stopping", "action_required")))
            .limit(1)
        ).scalar_one_or_none()
        if active_child is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot stop telemetry run while case-worker child run is active",
            )

    if run.run_kind == "case_worker":
        run.status = "stopped"
        run.stopped_at = datetime.utcnow()
        run.desired_case_count = 0
        run.blocked_reason = None
        add_run_event(
            db,
            run_id=run.id,
            environment_id=run.environment_id,
            event_type="run_stopped",
            message="Case-worker run stopped",
        )
        db.commit()
        db.refresh(run)
        return run

    active_states = ("active", "active_alert", "provisioning", "provision_failed")
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
        if run.run_kind == "case_worker":
            run.desired_case_count = run.profile.caseworker_worker_count_initial if run.profile is not None else 20
        else:
            run.desired_case_count = run.profile.device_count_initial if run.profile is not None else 50

    if run.run_kind == "case_worker":
        if run.parent_run_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Case-worker run has no parent run")
        parent_run = db.get(Run, run.parent_run_id)
        if parent_run is None or parent_run.status != "running":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parent telemetry run must be running before resume")

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

    child_exists = db.execute(select(Run.id).where(Run.parent_run_id == run.id).limit(1)).scalar_one_or_none()
    if child_exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Delete child case-worker runs before deleting this run")

    db.delete(run)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
