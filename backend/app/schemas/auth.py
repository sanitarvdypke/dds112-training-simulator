from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from app.models.entities import UserRole

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    full_name: str
    role: UserRole
    dds_service_key: str | None = None
