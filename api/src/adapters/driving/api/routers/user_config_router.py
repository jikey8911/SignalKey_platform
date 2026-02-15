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
    groqApiKey: Optional[str] = None
    gmgnApiKey: Optional[str] = None
    zeroExApiKey: Optional[str] = None
    telegramApiId: Optional[str] = None
    telegramApiHash: Optional[str] = None
    telegramPhoneNumber: Optional[str] = None
    telegramBotToken: Optional[str] = None
    telegramChatId: Optional[str] = None
    telegramChannels: Optional[Dict[str, List[str]]] = None
    investmentLimits: Optional[Dict[str, float]] = None
    virtualBalances: Optional[Dict[str, float]] = None
    botStrategy: Optional[Dict[str, Any]] = None
    # Exchanges (CEX) config (full replace on save)
    exchanges: Optional[List[ExchangeConfig]] = None



class TestAIRequest(BaseModel):
    provider: str
    apiKey: Optional[str] = None

class TestExchangeRequest(BaseModel):
    exchangeId: str
    apiKey: Optional[str] = None
    secret: Optional[str] = None
    password: Optional[str] = None
    uid: Optional[str] = None


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

        # Prefer exchanges from user_exchanges (with fallback to app_configs)
        try:
            config["exchanges"] = await config_repo.get_exchanges_prefer_user_exchanges(user_id, masked=True)
        except Exception:
            # keep whatever is in config
            pass

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
        
        # Filter out None values AND empty strings (avoid wiping secrets accidentally)
        update_dict = {}
        for k, v in updates.dict().items():
            if v is None:
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
            update_dict[k] = v

        if not update_dict:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        # Exchanges: UI sends full array, store it in user_exchanges (primary) + app_configs (copy)
        exchanges_payload = update_dict.pop("exchanges", None)
        if exchanges_payload is not None:
            try:
                # pydantic models -> dicts
                exchanges_list = [e.dict() if hasattr(e, "dict") else dict(e) for e in exchanges_payload]
                await config_repo.set_exchanges(user_id, exchanges_list)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to update exchanges: {str(e)}")

        # Update remaining config
        success = await config_repo.update_config(user_id, update_dict)

        if not success:
            # Try to create config if it doesn't exist
            await config_repo.create_config(user_id, update_dict)
        
        # Get updated config
        config = await config_repo.get_config(user_id)

        # Prefer exchanges from user_exchanges (with fallback to app_configs)
        if config is not None:
            try:
                config["exchanges"] = await config_repo.get_exchanges_prefer_user_exchanges(user_id, masked=True)
            except Exception:
                pass

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
        
        exchanges = await config_repo.get_exchanges_prefer_user_exchanges(user_id, masked=True)
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
        
        # Ensure config exists (secondary copy lives there)
        await config_repo.get_or_create_config(user_id)

        # Add exchange (writes primary user_exchanges + keeps copy in app_configs)
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



@router.post("/test-ai")
async def test_ai_connection(
    request: TestAIRequest,
    current_user: dict = Depends(get_current_user),
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Test AI connection"""
    try:
        user_id = current_user["openId"]
        
        # Determine API Key: Provided > Config > Env (handled by service/adapter)
        config = await config_repo.get_or_create_config(user_id)
        
        # If API key is provided in request, overlay it on config for the test
        test_config = config.copy() if config else {}
        if request.apiKey:
            # Map generic apiKey to specific field based on provider
            key_map = {
                "gemini": "geminiApiKey",
                "openai": "openaiApiKey",
                "perplexity": "perplexityApiKey",
                "grok": "grokApiKey"
            }
            if request.provider in key_map:
                test_config[key_map[request.provider]] = request.apiKey
            # Also set generic fields just in case
            test_config["aiApiKey"] = request.apiKey
            
        from api.main import ai_service
        
        success = await ai_service.test_connection(request.provider, test_config)
        
        if success:
            return {"status": "success", "message": f"Connected to {request.provider}"}
        else:
            return {"status": "error", "message": f"Failed to connect to {request.provider}"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing AI: {str(e)}")


@router.post("/test-exchange")
async def test_exchange_connection(
    request: TestExchangeRequest,
    current_user: dict = Depends(get_current_user),
    config_repo: ConfigRepository = Depends(get_config_repository)
):
    """Test Exchange connection"""
    try:
        user_id = current_user["openId"]
        
        from api.main import cex_service
        
        # If credentials provided, use them directly
        if request.apiKey and request.secret:
            success = await cex_service.test_connection(
                exchange_id=request.exchangeId,
                api_key=request.apiKey,
                secret=request.secret,
                password=request.password,
                uid=request.uid
            )
        else:
            # Use stored config
            # We need to fetch the specific exchange config
            config = await config_repo.get_or_create_config(user_id)
            exchanges = config.get("exchanges", [])
            target_ex = next((e for e in exchanges if e["exchangeId"] == request.exchangeId), None)
            
            if not target_ex:
                 raise HTTPException(status_code=404, detail="Exchange not found in config and no credentials provided")
            
            success = await cex_service.test_connection(
                exchange_id=target_ex["exchangeId"],
                api_key=target_ex["apiKey"],
                secret=target_ex["secret"],
                password=target_ex.get("password"),
                uid=target_ex.get("uid")
            )

        if success:
            return {"status": "success", "message": f"Connected to {request.exchangeId}"}
        else:
             return {"status": "error", "message": f"Failed to connect to {request.exchangeId}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing Exchange: {str(e)}")
