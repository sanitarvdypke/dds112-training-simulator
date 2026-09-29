from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    member_ids: list[UUID] = Field(default_factory=list)


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    member_ids: list[UUID] | None = None


class GroupMemberOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    dds_service_key: str | None = None


class GroupOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    members: list[GroupMemberOut]

