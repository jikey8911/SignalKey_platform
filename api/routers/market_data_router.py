from fastapi import APIRouter, HTTPException
from typing import List
import logging
from api.services.ccxt_service import ccxt_service
import ccxt.async_support as ccxt # Keep for ccxt.exchanges list (static)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market-data"])

@router.get("/exchanges", response_model=List[str])
async def list_exchanges():
    """
    Retorna la lista de todos los exchanges soportados por CCXT.
    """
    return ccxt.exchanges

@router.get("/exchanges/{exchange_id}/markets", response_model=List[str])
async def list_market_types(exchange_id: str):
    """
    Retorna los tipos de mercado disponibles (spot, swap, future, margin) para un exchange.
    Delegado a CCXTService.
    """
    markets = await ccxt_service.get_markets(exchange_id)
    if not markets:
        # Check if exchange exists in list or service returned empty due to error
        if exchange_id not in ccxt.exchanges:
             raise HTTPException(status_code=404, detail="Exchange not found")
        # If empty but valid exchange, return empty list
        return []
    return markets

@router.get("/exchanges/{exchange_id}/markets/{market_type}/symbols", response_model=List[str])
async def list_symbols(exchange_id: str, market_type: str):
    """
    Retorna la lista de símbolos activos para un exchange y tipo de mercado específico.
    Delegado a CCXTService.
    """
    symbols = await ccxt_service.get_symbols(exchange_id, market_type)
    return symbols
