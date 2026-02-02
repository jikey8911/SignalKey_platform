from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os

from api.src.adapters.driven.database.config_repository import ConfigRepository
from api.src.adapters.driven.database.mongodb_connection import get_database
from api.src.infrastructure.security.auth_deps import get_current_user

router = APIRouter(prefix="/config", tags=["configuration"])


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


@router.get("/")
async def get_config(
    current_user: dict = Depends(get_current_user),
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Get user configuration"""
    try:
        user_id = current_user["openId"]
        
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


@router.put("/")
async def update_config(
    updates: ConfigUpdate,
    current_user: dict = Depends(get_current_user),
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Update user configuration"""
    try:
        user_id = current_user["openId"]
        
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


@router.get("/exchanges")
async def get_exchanges(
    current_user: dict = Depends(get_current_user),
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Get user's configured exchanges"""
    try:
        user_id = current_user["openId"]
        
        config = await config_repo.get_or_create_config(user_id)
        exchanges = config.get('exchanges', [])
        
        return {"exchanges": exchanges}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/exchanges")
async def add_exchange(
    exchange: ExchangeConfig,
    current_user: dict = Depends(get_current_user),
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Add exchange to user configuration"""
    try:
        user_id = current_user["openId"]
        
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


@router.delete("/exchanges/{exchange_id}")
async def remove_exchange(
    exchange_id: str,
    current_user: dict = Depends(get_current_user),
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Remove exchange from user configuration"""
    try:
        user_id = current_user["openId"]
        
        success = await config_repo.remove_exchange(user_id, exchange_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Exchange not found")
        
        return {"success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
