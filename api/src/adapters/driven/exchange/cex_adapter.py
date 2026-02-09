import logging
from typing import List, Optional, Dict
from api.src.domain.services.exchange_port import IExchangePort
from api.src.domain.entities.trading import Ticker, Balance, Order, TradeResult
from api.src.domain.entities.signal import SignalAnalysis
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
from api.src.adapters.driven.persistence.mongodb import get_app_config, save_trade, update_virtual_balance, db
from datetime import datetime

logger = logging.getLogger(__name__)

class CEXAdapter(IExchangePort):
    """
    Adapter for Centralized Exchanges (CEX).
    Implements IExchangePort and delegates to CCXTService or internal logic.
    """ 

    def _normalize_symbol(self, symbol: str) -> str:
        """Matches legacy logic to normalize symbols."""
        if not symbol or not str(symbol).strip(): 
            return "UNKNOWN/USDT"
        
        symbol = str(symbol).upper().strip().replace("-", "/").replace("_", "/")
        
        if "/" not in symbol:
            for quote in ["USDT", "USDC", "BUSD", "BTC", "ETH"]:
                if symbol.endswith(quote) and symbol != quote:
                    return f"{symbol[:-len(quote)]}/{quote}"
        return symbol

    async def get_current_price(self, symbol: str, user_id: str) -> float:
        symbol = self._normalize_symbol(symbol)
        try:
            config = await get_app_config(user_id)
            active_exchanges = []
            
            if config and config.get("exchanges"):
                active_exchanges = [e for e in config["exchanges"] if e.get("isActive", True)]

            # 1. Search in user's active exchanges
            for ex_cfg in active_exchanges:
                ex_id = ex_cfg["exchangeId"]
                try:
                    # Usamos el método unificado _get_exchange que maneja credenciales internamente
                    instance = await ccxt_service._get_exchange(ex_id, user_id)
                    
                    if instance:
                         if not instance.markets: await instance.load_markets()
                         # Intentar obtener ticker de CCXT directamente
                         ticker = await instance.fetch_ticker(symbol)
                         return float(ticker['last'])

                except Exception as e:
                    logger.debug(f"CEXAdapter: {ex_id} failed for {symbol}: {e}")

            # 2. Fallback if no active exchanges found 
            # (In legacy this returned 0.0, we keep that behavior)
            return 0.0

        except Exception as e:
            logger.error(f"CEXAdapter: Price fetch error {symbol}: {e}")
            return 0.0

    async def fetch_balance(self, user_id: str, exchange_id: Optional[str] = None) -> List[Balance]:
        """
        Fetches balance using the specified exchange_id from user config.
        If exchange_id is None, it uses the first active exchange.
        """
        try:
            config = await get_app_config(user_id)
            exchanges_config = config.get("exchanges", []) if config else []
            
            ex_cfg = None
            if exchange_id:
                ex_cfg = next((e for e in exchanges_config if e["exchangeId"] == exchange_id and e.get("isActive", True)), None)
            else:
                ex_cfg = next((e for e in exchanges_config if e.get("isActive", True)), None)
            
            if not ex_cfg:
                 logger.warning(f"CEXAdapter: No active exchange config found for user {user_id}")
                 return []

            # Call unified fetch_balance method
            balances_list = await ccxt_service.fetch_balance(
                user_id,
                ex_cfg["exchangeId"]
            )
            return balances_list

        except Exception as e:
            logger.error(f"CEXAdapter: Balance fetch error: {e}")
            return []

    async def execute_trade(self, analysis: SignalAnalysis, user_id: str) -> TradeResult:
        try:
            config = await get_app_config(user_id)
            if not config:
                 return TradeResult(success=False, message="User config not found")

            # Determine which exchange to use (first active or specific if logic allows)
            # Legacy logic just picked first active
            exchanges_config = config.get("exchanges", [])
            ex_cfg = next((e for e in exchanges_config if e.get("isActive", True)), None)
            
            demo_mode = config.get("demoMode", True)
            
            # --- DEMO MODE LOGIC ---
            if demo_mode:
                # Re-using legacy demo logic but cleaner
                symbol = self._normalize_symbol(analysis.symbol)
                price = await self.get_current_price(symbol, user_id)
                
                # Logic largely copied from legacy for consistency
                amount = analysis.parameters.amount if analysis.parameters.amount else 0
                max_amount = config.get("investmentLimits", {}).get("cexMaxAmount", 100.0)
                amount = min(amount, max_amount) if amount > 0 else max_amount

                if price <= 0:
                     return TradeResult(success=False, message=f"Could not fetch price for {symbol}")

                entry_price = analysis.parameters.entry_price or price
                side = str(analysis.decision.value).lower() # Decision is Enun

                trade_doc = {
                    "userId": config["userId"],
                    "symbol": symbol,
                    "side": side.upper(),
                    "entryPrice": entry_price,
                    "currentPrice": price,
                    "amount": amount,
                    "marketType": str(analysis.market_type.name),
                    "isDemo": True,
                    "status": "pending", # Logic simplification
                    "tp": [tp.__dict__ for tp in analysis.parameters.tp],
                    "sl": analysis.parameters.sl,
                    "createdAt": datetime.utcnow()
                }
                
                # If price is good, open immediately
                if (side == "buy" and price <= entry_price) or (side == "sell" and price >= entry_price):
                    trade_doc["status"] = "open"
                    # Update virtual balance logic... (Simplified for this adapter)
                    await update_virtual_balance(user_id, "CEX", "USDT", -amount if side=="buy" else amount, is_relative=True)

                await save_trade(trade_doc)
                return TradeResult(success=True, message=f"DEMO Trade {side} {symbol} simulated at {price}")

            # --- REAL MODE LOGIC ---
            if not ex_cfg:
                 return TradeResult(success=False, message="No active exchange for real trading")

            trade_result_dict = await ccxt_service.execute_trade(
                symbol=symbol,
                side=side,
                amount=amount,
                price=analysis.parameters.entry_price,
                user_id=user_id,
                exchange_id=ex_cfg["exchangeId"]
            )

            if trade_result_dict.get("success"):
                return TradeResult(
                    success=True, 
                    message="Order executed", 
                    order_id=trade_result_dict.get('order_id'),
                    price=trade_result_dict.get('details', {}).get('average'),
                    amount=trade_result_dict.get('details', {}).get('amount')
                )
            else:
                return TradeResult(success=False, message=trade_result_dict.get("message", "Execution failed"))

        except Exception as e:
            logger.error(f"CEXAdapter: Trade execution failed: {e}")
            return TradeResult(success=False, message=str(e))

    async def fetch_open_orders(self, user_id: str, symbol: Optional[str] = None) -> List[Order]:
        try:
            config = await get_app_config(user_id)
            ex_cfg = next((e for e in config.get("exchanges", []) if e.get("isActive", True)), None)
            if not ex_cfg: return []

            orders_dict = await ccxt_service.fetch_open_orders(
                symbol=self._normalize_symbol(symbol) if symbol else None,
                user_id=user_id,
                exchange_id=ex_cfg["exchangeId"]
            )
            
            from api.src.domain.entities.trading import Order
            return [Order(**o) if isinstance(o, dict) else o for o in orders_dict]
        except Exception as e:
            logger.error(f"CEXAdapter: Error fetching open orders: {e}")
            return []

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int = 15000, use_random_date: bool = False, user_id: str = "default_user", exchange_id: str = "binance") -> Any:
        return await ccxt_service.get_historical_data(
            symbol=self._normalize_symbol(symbol),
            timeframe=timeframe,
            limit=limit,
            user_id=user_id,
            exchange_id=exchange_id,
            use_random_date=use_random_date
        )

    async def get_markets(self, exchange_id: str) -> List[str]:
        return await ccxt_service.get_markets(exchange_id)

    async def get_symbols(self, exchange_id: str, market_type: str) -> List[str]:
        return await ccxt_service.get_symbols(exchange_id, market_type)
