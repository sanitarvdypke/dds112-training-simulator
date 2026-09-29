from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.entities import User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.core.security import verify_password, create_access_token
from app.api.deps import current_user

router=APIRouter(prefix="/auth", tags=["auth"])
@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession=Depends(get_db)):
    user=await db.scalar(select(User).where(User.email==data.email))
    if not user or not user.is_active or not verify_password(data.password,user.password_hash): raise HTTPException(401,"Неверный логин или пароль")
    return TokenResponse(access_token=create_access_token(str(user.id),user.role.value))
@router.get("/me", response_model=UserOut)
async def me(user: User=Depends(current_user)): return user
