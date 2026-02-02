from fastapi import APIRouter, HTTPException
from typing import List
import logging
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
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

@router.get("/candles")
async def get_candles(symbol: str, timeframe: str = "1h", limit: int = 100):
    """
    Get historical candles for charts.
    """
    try:
        # We use the public data fetcher which is robust
        df = await ccxt_service.get_public_historical_data(symbol, timeframe, limit=limit)
        
        if df.empty:
             return []
             
        # Convert to list of dicts for frontend {time, open, high, low, close, volume}
        # Timestamp in df index is datetime64, convert to int timestamp (seconds)
        data = []
        for timestamp, row in df.iterrows():
            data.append({
                "time": int(timestamp.timestamp()), # Frontend charts usually expect seconds
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close'],
                "volume": row['volume']
            })
        return data
        
    except Exception as e:
        logger.error(f"Error fetching candles for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
