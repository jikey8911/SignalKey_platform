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
    try:
        markets = await ccxt_service.get_markets(exchange_id)
    except Exception as e:
        logger.error(f"Error fetching markets for {exchange_id}: {e}")
        raise HTTPException(status_code=503, detail=f"No se pudieron obtener mercados para {exchange_id}. Verifica conexión DNS/Internet. Error: {str(e)}")

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
    try:
        symbols = await ccxt_service.get_symbols(exchange_id, market_type)
    except Exception as e:
        logger.error(f"Error fetching symbols for {exchange_id} ({market_type}): {e}")
        raise HTTPException(status_code=503, detail=f"No se pudieron obtener símbolos para {exchange_id}/{market_type}. Verifica conexión DNS/Internet. Error: {str(e)}")
    return symbols

@router.get("/candles")
async def get_candles(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 300,
    exchange_id: str = "binance",
    market_type: str = "spot",
):
    """
    Get historical candles for charts.
    """
    try:
        # Public historical candles resolved by exchange + market type.
        df = await ccxt_service.get_historical_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            exchange_id=exchange_id,
            market_type=market_type,
        )

        if df.empty:
             return []

        data = []
        for timestamp, row in df.iterrows():
            data.append({
                "time": int(timestamp.timestamp()),
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": float(row['volume'])
            })
        return data

    except Exception as e:
        logger.error(f"Error fetching candles for {symbol} ({exchange_id}/{market_type}/{timeframe}): {e}")
        raise HTTPException(status_code=503, detail=str(e))
