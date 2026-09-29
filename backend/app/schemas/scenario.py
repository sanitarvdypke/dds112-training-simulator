from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from typing import Any
class ScenarioCreate(BaseModel):
    code: str = Field(min_length=1,max_length=100,pattern=r"\S")
    title: str = Field(min_length=1,max_length=255,pattern=r"\S")
    category: str = Field(min_length=1,max_length=255,pattern=r"\S")
    time_limit_sec: int = Field(120,ge=1,le=3600,exclude=True)
    difficulty: int = Field(1, ge=1, le=5)
    participant_role: str = "Заявитель"
    incident_payload: dict[str, Any] = {}
    expected_state: dict[str, Any] = {}
    published: bool = False
class ScenarioOut(ScenarioCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
