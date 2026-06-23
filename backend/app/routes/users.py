from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import User
from app.schemas import UserCreate, UserOut, UserPasswordReset, UserUpdate
from app.security import hash_password

router = APIRouter(prefix="/api/sim/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[UserOut]:
    stmt = select(User).order_by(User.email.asc())
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> UserOut:
    existing = db.execute(select(User).where(User.email == payload.email.lower().strip())).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User email already exists")

    user = User(
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
        is_admin=payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updates = payload.model_dump(exclude_unset=True)
    if "is_admin" in updates and updates["is_admin"] is False and user.is_admin:
        active_admin_count = (
            db.execute(select(func.count(User.id)).where(User.is_admin.is_(True), User.is_active.is_(True))).scalar_one() or 0
        )
        if active_admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot remove last active admin")
    if "is_active" in updates and updates["is_active"] is False and user.is_admin:
        active_admin_count = (
            db.execute(select(func.count(User.id)).where(User.is_admin.is_(True), User.is_active.is_(True))).scalar_one() or 0
        )
        if active_admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot deactivate last active admin")

    for key, value in updates.items():
        setattr(user, key, value)

    if user.id == current_admin.id and not user.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot deactivate your own account")

    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def reset_password(
    user_id: int,
    payload: UserPasswordReset,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.password_hash = hash_password(payload.password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(require_admin)) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete your own account")
    if user.is_admin:
        active_admin_count = (
            db.execute(select(func.count(User.id)).where(User.is_admin.is_(True), User.is_active.is_(True))).scalar_one() or 0
        )
        if active_admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete last active admin")

    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
