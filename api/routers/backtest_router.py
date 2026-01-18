"""
Endpoints para backtesting - Exchanges, Markets y Symbols
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
import logging
from api.models.mongodb import db
from api.services.ccxt_service import ccxt_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/exchanges/{user_id}")
async def get_user_exchanges(user_id: str):
    """
    Obtiene los exchanges configurados del usuario
    
    Args:
        user_id: ID del usuario (openId)
    
    Returns:
        Lista de exchanges configurados con su estado
    """
    try:
        # Buscar usuario
        user = await db.users.find_one({"openId": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Obtener configuración
        config = await db.app_configs.find_one({"userId": user["_id"]})
        if not config or not config.get("exchanges"):
            return []
        
        # Retornar exchanges activos
        exchanges = config.get("exchanges", [])
        active_exchanges = [
            {
                "exchangeId": ex.get("exchangeId"),
                "isActive": ex.get("isActive", True)
            }
            for ex in exchanges
            if ex.get("isActive", True)
        ]
        
        logger.info(f"Found {len(active_exchanges)} active exchanges for user {user_id}")
        return active_exchanges
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching exchanges for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markets/{user_id}/{exchange_id}")
async def get_exchange_markets(user_id: str, exchange_id: str):
    """
    Obtiene los tipos de mercado disponibles para un exchange
    
    Args:
        user_id: ID del usuario
        exchange_id: ID del exchange (ej: 'okx', 'binance')
    
    Returns:
        Lista de tipos de mercado disponibles
    """
    try:
        # Verificar que el usuario existe
        user = await db.users.find_one({"openId": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Obtener mercados del exchange
        markets = await ccxt_service.get_markets(exchange_id)
        
        logger.info(f"Found {len(markets)} markets for exchange {exchange_id}")
        return {"markets": markets}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching markets for {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/{user_id}/{exchange_id}")
async def get_exchange_symbols(
    user_id: str, 
    exchange_id: str, 
    market_type: Optional[str] = "spot"
):
    """
    Obtiene los símbolos con datos de precio para un exchange y tipo de mercado
    
    Args:
        user_id: ID del usuario
        exchange_id: ID del exchange
        market_type: Tipo de mercado (spot, future, swap, etc.)
    
    Returns:
        Lista de símbolos con precio actual y cambio porcentual
    """
    try:
        # Verificar que el usuario existe
        user = await db.users.find_one({"openId": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Obtener símbolos con tickers
        symbols = await ccxt_service.get_symbols_with_tickers(exchange_id, market_type)
        
        logger.info(f"Found {len(symbols)} symbols for {exchange_id} ({market_type})")
        return {"symbols": symbols}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching symbols for {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
