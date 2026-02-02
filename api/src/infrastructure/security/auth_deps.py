from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import jwt
import os
from api.config import Config
from api.src.adapters.driven.database.user_repository import UserRepository
from api.src.adapters.driven.database.mongodb_connection import get_database

SECRET_KEY = Config.JWT_SECRET
ALGORITHM = "HS256"

async def get_user_repository() -> UserRepository:
    db = await get_database()
    return UserRepository(db)

async def get_current_user(
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository)
) -> dict:
    """
    Extracts user ID from JWT token in cookie or Authorization header.
    Returns the user document.
    """
    token = request.cookies.get("manus.sid")
    
    # Fallback to Authorization header if no cookie
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        openid = payload.get("openId")
        if not openid:
            raise HTTPException(status_code=401, detail="Invalid token payload")
            
        user = await user_repo.find_user_by_openid(openid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        return user
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
