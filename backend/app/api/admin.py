from datetime import datetime, timezone
import os
import shutil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.models.entities import AuditLog, SessionStatus, TrainingSession, User, UserRole
from app.schemas.admin import AdminUserCreate, AdminUserOut, AdminUserUpdate
from app.services.audit import audit

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN)),
):
    return (await db.scalars(select(User).order_by(User.role, User.email))).all()


@router.post("/users", response_model=AdminUserOut)
async def create_user(
    data: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN)),
):
    email = data.email.strip().lower()
    name = data.full_name.strip()
    if not name:
        raise HTTPException(422, "Укажите имя пользователя")
    if await db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(409, "Пользователь с таким логином уже существует")
    row = User(email=email, full_name=name, password_hash=hash_password(data.password), role=data.role)
    db.add(row)
    await db.flush()
    await audit(db, user.id, "USER_CREATED", "User", row.id, {"role": row.role.value})
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: UUID,
    data: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN)),
):
    row = await db.get(User, user_id, with_for_update=True)
    if not row:
        raise HTTPException(404, "Пользователь не найден")
    if row.id == user.id and (data.is_active is False or data.role not in (None, UserRole.ADMIN)):
        raise HTTPException(409, "Нельзя отключить свою учётную запись или снять с неё роль администратора")
    changed = {}
    if data.role is not None and data.role != row.role:
        row.role = data.role
        changed["role"] = data.role.value
    if data.is_active is not None and data.is_active != row.is_active:
        row.is_active = data.is_active
        changed["is_active"] = data.is_active
    if changed:
        await audit(db, user.id, "USER_UPDATED", "User", row.id, changed)
        await db.commit()
        await db.refresh(row)
    return row


@router.get("/system")
async def system_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN)),
):
    total_users = await db.scalar(select(func.count()).select_from(User))
    active_users = await db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True)))
    audit_events = await db.scalar(select(func.count()).select_from(AuditLog))
    rows = (await db.execute(select(TrainingSession.status, func.count()).group_by(TrainingSession.status))).all()
    sessions = {status.value: count for status, count in rows}
    disk = shutil.disk_usage("/")
    try:
        memory_total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        memory_available = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        memory_total = memory_available = None
    try:
        load_average = [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        load_average = None
    return {
        "status": "ok",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mode": settings.app_env,
        "database": "available",
        "providers": {"ai": settings.ai_provider, "call": "disabled for DDS cards", "rtu": settings.rtu_provider},
        "users": {"total": total_users, "active": active_users},
        "sessions": {status.value: sessions.get(status.value, 0) for status in SessionStatus},
        "audit_events": audit_events,
        "host": {
            "cpu_count": os.cpu_count(),
            "load_average": load_average,
            "memory_total_bytes": memory_total,
            "memory_available_bytes": memory_available,
            "disk_total_bytes": disk.total,
            "disk_free_bytes": disk.free,
        },
    }
