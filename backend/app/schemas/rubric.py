from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.services.dds_card import DDS_STATUSES, DDS_FIELDS

class RubricStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    weight: int = Field(default=2, ge=1, le=20)
    within_sec: int | None = Field(default=None, ge=1, le=3600)
    anchor: Literal["RECEIVED", "PREVIOUS"] = "RECEIVED"
    require_comment: bool = False

class Rubric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[RubricStep] = Field(min_length=1, max_length=7)
    total_time_sec: int = Field(default=600, ge=1, le=3600)
    require_comment: bool = True
    required_fields: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def valid_rules(self):
        statuses = [s.status for s in self.steps]
        if len(set(statuses)) != len(statuses) or any(s not in DDS_STATUSES for s in statuses):
            raise ValueError("Статусы эталона должны быть допустимыми и не повторяться")
        if self.steps[0].anchor != "RECEIVED": raise ValueError("Первый норматив отсчитывается от получения карточки")
        if len(set(self.required_fields)) != len(self.required_fields) or not set(self.required_fields) <= DDS_FIELDS.keys():
            raise ValueError("Некорректные обязательные поля ДДС")
        return self
