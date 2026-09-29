from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.entities import User, UserRole
from app.core.security import decode_token

bearer = HTTPBearer()
async def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: AsyncSession = Depends(get_db)) -> User:
    try: payload = decode_token(credentials.credentials)
    except Exception as exc: raise HTTPException(status_code=401, detail="Недействительный токен") from exc
    user = await db.scalar(select(User).where(User.id == payload.get("sub")))
    if not user or not user.is_active: raise HTTPException(status_code=401, detail="Пользователь недоступен")
    return user

def require_roles(*roles: UserRole):
    async def checker(user: User = Depends(current_user)):
        if user.role not in roles: raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return user
    return checker
