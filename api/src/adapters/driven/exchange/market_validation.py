from __future__ import annotations

import logging
from typing import Optional

from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

logger = logging.getLogger(__name__)


def _sanitize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().replace("#", "")
    return s


async def is_symbol_supported(exchange_id: str, symbol: str, market_type: Optional[str] = None) -> bool:
    """Validate that symbol exists on exchange for the given market type.

    Uses ccxt.pro exchange.load_markets() (cached) and checks exchange.markets.
    """
    try:
        ex = await ccxt_service._get_exchange(exchange_id, market_type=market_type)
        sym = _sanitize_symbol(symbol)
        if not sym:
            return False
        markets = getattr(ex, "markets", None) or {}
        return sym in markets
    except Exception as e:
        logger.warning(f"symbol validation failed for {exchange_id} {symbol} {market_type}: {e}")
        return False
