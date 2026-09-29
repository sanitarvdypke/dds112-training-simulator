import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.entities import Group, GroupMember, TrainingSession, User, UserRole
from app.schemas.groups import GroupCreate, GroupOut, GroupUpdate
from app.services.audit import audit

router = APIRouter(prefix="/groups", tags=["groups"])
staff = require_roles(UserRole.ADMIN, UserRole.TEACHER)


async def member_rows(db: AsyncSession, group_id: uuid.UUID):
    return (await db.scalars(
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
        .order_by(User.full_name, User.email)
    )).all()


async def serialize(db: AsyncSession, row: Group) -> GroupOut:
    members = await member_rows(db, row.id)
    return GroupOut(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        members=[{
            "id": member.id,
            "full_name": member.full_name,
            "email": member.email,
            "dds_service_key": member.dds_service_key,
        } for member in members],
    )


async def validate_members(db: AsyncSession, member_ids: list[uuid.UUID]):
    unique = set(member_ids)
    if not unique:
        return unique
    valid = set((await db.scalars(
        select(User.id).where(
            User.id.in_(unique),
            User.role == UserRole.STUDENT,
            User.is_active.is_(True),
        )
    )).all())
    if valid != unique:
        raise HTTPException(422, "В группу можно добавить только активных обучающихся")
    return unique


@router.get("", response_model=list[GroupOut])
async def list_groups(db: AsyncSession = Depends(get_db), user: User = Depends(staff)):
    rows = (await db.scalars(select(Group).order_by(Group.name))).all()
    return [await serialize(db, row) for row in rows]


@router.post("", response_model=GroupOut)
async def create_group(data: GroupCreate, db: AsyncSession = Depends(get_db), user: User = Depends(staff)):
    name = data.name.strip()
    if await db.scalar(select(Group.id).where(func.lower(Group.name) == name.lower())):
        raise HTTPException(409, "Группа с таким названием уже существует")
    member_ids = await validate_members(db, data.member_ids)
    row = Group(name=name)
    db.add(row)
    await db.flush()
    db.add_all([GroupMember(group_id=row.id, user_id=member_id) for member_id in member_ids])
    await audit(db, user.id, "GROUP_CREATED", "Group", row.id, {"name": name, "members": len(member_ids)})
    await db.commit()
    await db.refresh(row)
    return await serialize(db, row)


@router.put("/{group_id}", response_model=GroupOut)
async def update_group(group_id: uuid.UUID, data: GroupUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(staff)):
    row = await db.get(Group, group_id, with_for_update=True)
    if not row:
        raise HTTPException(404, "Группа не найдена")
    changes = {}
    if data.name is not None:
        name = data.name.strip()
        duplicate = await db.scalar(select(Group.id).where(func.lower(Group.name) == name.lower(), Group.id != group_id))
        if duplicate:
            raise HTTPException(409, "Группа с таким названием уже существует")
        if name != row.name:
            row.name = name
            changes["name"] = name
    if data.member_ids is not None:
        member_ids = await validate_members(db, data.member_ids)
        await db.execute(delete(GroupMember).where(GroupMember.group_id == group_id))
        db.add_all([GroupMember(group_id=group_id, user_id=member_id) for member_id in member_ids])
        changes["members"] = len(member_ids)
    if changes:
        await audit(db, user.id, "GROUP_UPDATED", "Group", row.id, changes)
        await db.commit()
        await db.refresh(row)
    return await serialize(db, row)


@router.delete("/{group_id}")
async def delete_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(staff)):
    row = await db.get(Group, group_id, with_for_update=True)
    if not row:
        raise HTTPException(404, "Группа не найдена")
    if await db.scalar(select(TrainingSession.id).where(TrainingSession.group_id == group_id)):
        raise HTTPException(409, "Группа уже используется в занятиях и не может быть удалена")
    await audit(db, user.id, "GROUP_DELETED", "Group", row.id, {"name": row.name})
    await db.delete(row)
    await db.commit()
    return {"ok": True}
