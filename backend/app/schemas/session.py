from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from typing import Any
class TrainingSessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255, pattern=r"\S")
    group_id: UUID | None = None
    scenario_ids: list[UUID] = Field(min_length=1)
class TrainingSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    status: str
    group_id: UUID | None = None
    scenario_ids: list[str]
class ActionCreate(BaseModel):
    action_type: str
    payload: dict[str, Any] = {}
class CompleteCallOut(BaseModel):
    score: float
    max_score: float
    duration_sec: int
    over_time: bool
    details: dict[str, Any]
    ai_feedback: dict[str, Any]
