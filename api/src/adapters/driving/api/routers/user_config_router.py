from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import jwt
import os

from api.src.adapters.driven.database.config_repository import ConfigRepository
from api.src.adapters.driven.database.mongodb_connection import get_database

router = APIRouter(prefix="/config", tags=["configuration"])

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
ALGORITHM = "HS256"


class ExchangeConfig(BaseModel):
    exchangeId: str
    apiKey: str
    secret: str
    password: Optional[str] = None
    uid: Optional[str] = None
    isActive: bool = True


class ConfigUpdate(BaseModel):
    demoMode: Optional[bool] = None
    isAutoEnabled: Optional[bool] = None
    aiProvider: Optional[str] = None
    geminiApiKey: Optional[str] = None
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None
    grokApiKey: Optional[str] = None
    gmgnApiKey: Optional[str] = None
    zeroExApiKey: Optional[str] = None
    telegramApiId: Optional[str] = None
    telegramApiHash: Optional[str] = None
    telegramPhoneNumber: Optional[str] = None
    telegramBotToken: Optional[str] = None
    telegramChatId: Optional[str] = None
    investmentLimits: Optional[Dict[str, float]] = None
    virtualBalances: Optional[Dict[str, float]] = None


async def get_config_repository() -> ConfigRepository:
    """Dependency to get config repository"""
    db = await get_database()
    return ConfigRepository(db)


async def get_current_user_id(request: Request) -> str:
    """Extract user ID from JWT token"""
    token = request.cookies.get("manus.sid")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        openid = payload.get("openId")
        if not openid:
            raise HTTPException(status_code=401, detail="Invalid token")
        return openid
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/{user_id}")
async def get_config(
    user_id: str,
    request: Request,
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Get user configuration"""
    try:
        # Verify user is requesting their own config
        current_user = await get_current_user_id(request)
        if current_user != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Get or create config
        config = await config_repo.get_or_create_config(user_id)
        
        # Remove sensitive fields from response
        if config and '_id' in config:
            config['_id'] = str(config['_id'])
        if config and 'userId' in config:
            config['userId'] = str(config['userId'])
        
        return {"config": config}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/{user_id}")
async def update_config(
    user_id: str,
    updates: ConfigUpdate,
    request: Request,
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Update user configuration"""
    try:
        # Verify user is updating their own config
        current_user = await get_current_user_id(request)
        if current_user != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Filter out None values
        update_dict = {k: v for k, v in updates.dict().items() if v is not None}
        
        if not update_dict:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        # Update config
        success = await config_repo.update_config(user_id, update_dict)
        
        if not success:
            # Try to create config if it doesn't exist
            await config_repo.create_config(user_id, update_dict)
        
        # Get updated config
        config = await config_repo.get_config(user_id)
        
        if config and '_id' in config:
            config['_id'] = str(config['_id'])
        if config and 'userId' in config:
            config['userId'] = str(config['userId'])
        
        return {"success": True, "config": config}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{user_id}/exchanges")
async def get_exchanges(
    user_id: str,
    request: Request,
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Get user's configured exchanges"""
    try:
        # Verify user is requesting their own exchanges
        current_user = await get_current_user_id(request)
        if current_user != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        config = await config_repo.get_or_create_config(user_id)
        exchanges = config.get('exchanges', [])
        
        return {"exchanges": exchanges}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/{user_id}/exchanges")
async def add_exchange(
    user_id: str,
    exchange: ExchangeConfig,
    request: Request,
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Add exchange to user configuration"""
    try:
        # Verify user is adding to their own config
        current_user = await get_current_user_id(request)
        if current_user != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Ensure config exists
        await config_repo.get_or_create_config(user_id)
        
        # Add exchange
        success = await config_repo.add_exchange(user_id, exchange.dict())
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add exchange")
        
        return {"success": True, "exchange": exchange.dict()}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/{user_id}/exchanges/{exchange_id}")
async def remove_exchange(
    user_id: str,
    exchange_id: str,
    request: Request,
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Remove exchange from user configuration"""
    try:
        # Verify user is removing from their own config
        current_user = await get_current_user_id(request)
        if current_user != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        success = await config_repo.remove_exchange(user_id, exchange_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Exchange not found")
        
        return {"success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
