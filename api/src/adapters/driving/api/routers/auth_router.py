from fastapi import APIRouter, HTTPException, Depends, Response, Request
from pydantic import BaseModel
from typing import Optional
import jwt
from datetime import datetime, timedelta
import os

from api.src.adapters.driven.database.user_repository import UserRepository
from api.src.adapters.driven.database.mongodb_connection import get_database

router = APIRouter(prefix="/auth", tags=["authentication"])

# JWT Configuration
from api.config import Config
SECRET_KEY = Config.JWT_SECRET
print(f"[AUTH] JWT Secret prefix: {SECRET_KEY[:4]}... (len: {len(SECRET_KEY)})")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 365

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    success: bool
    user: Optional[dict] = None
    token: Optional[str] = None
    error: Optional[str] = None


def create_access_token(data: dict) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_user_repository() -> UserRepository:
    """Dependency to get user repository"""
    db = await get_database()
    return UserRepository(db)


@router.post("/register", response_model=AuthResponse)
async def register(
    request: RegisterRequest,
    response: Response,
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Register a new user"""
    try:
        # Check if user already exists
        existing_user = await user_repo.find_user_by_openid(request.username)
        if existing_user:
            raise HTTPException(status_code=409, detail="User already exists")
        
        # Create new user
        user_data = {
            'openId': request.username,
            'name': request.username,
            'role': 'user',
            'password': request.password  # Will be hashed in repository
        }
        
        new_user = await user_repo.create_user(user_data)
        
        # Create JWT token
        token = create_access_token({
            'openId': request.username,
            'appId': os.getenv('VITE_APP_ID', 'signalkey-dev'),
            'name': request.username
        })
        
        # Set cookie
        response.set_cookie(
            key="manus.sid",
            value=token,
            httponly=True,
            secure=os.getenv('NODE_ENV') == 'production',
            max_age=365 * 24 * 60 * 60,  # 1 year in seconds
            path="/"
        )
        
        return AuthResponse(
            success=True,
            user={'openId': new_user['openId'], 'name': new_user.get('name', request.username)},
            token=token
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    response: Response,
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Login user"""
    try:
        # Verify user exists
        user = await user_repo.find_user_by_openid(request.username)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        is_valid = await user_repo.verify_password(request.username, request.password)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Create JWT token
        token = create_access_token({
            'openId': user['openId'],
            'appId': os.getenv('VITE_APP_ID', 'signalkey-dev'),
            'name': user.get('name', request.username)
        })
        
        # Set cookie
        response.set_cookie(
            key="manus.sid",
            value=token,
            httponly=True,
            secure=os.getenv('NODE_ENV') == 'production',
            max_age=365 * 24 * 60 * 60,
            path="/"
        )
        
        # Update last signed in
        await user_repo.update_last_signed_in(request.username)
        
        return AuthResponse(
            success=True,
            user={'openId': user['openId'], 'name': user.get('name', request.username)},
            token=token
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/logout")
async def logout(response: Response):
    """Logout user"""
    response.delete_cookie(key="manus.sid", path="/")
    return {"success": True}


@router.get("/me")
async def get_current_user(
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Get current authenticated user"""
    try:
        # Get token from cookie
        token = request.cookies.get("manus.sid")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # Decode JWT
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            openid = payload.get("openId")
            if not openid:
                raise HTTPException(status_code=401, detail="Invalid token")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get user from database
        user = await user_repo.find_user_by_openid(openid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            'user': {
                'openId': user['openId'],
                'name': user.get('name'),
                'email': user.get('email'),
                'role': user.get('role', 'user')
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
