"""
Endpoints para backtesting - Exchanges, Markets y Symbols
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime
import os
from api.src.adapters.driven.persistence.mongodb import db
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
from api.src.application.services.ml_service import MLService
from api.src.application.services.ai_service import AIService
from api.src.domain.entities.bot_instance import BotInstance
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.infrastructure.security.auth_deps import get_current_user
from api.src.domain.models.schemas import StrategyOptimizationRequest, StrategyOptimizationResponse, StrategyOptimizeRunRequest, SaveStrategyRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/exchanges/{user_id}")
async def get_user_exchanges(user_id: str):
    # ... (Keep existing GET endpoints for now or refactor them later if needed)
    # Since the user specifically asked about the POST /run error, we focus there first.
    pass 

# ... (omitting GET endpoints implementation in replacement to save tokens, assuming target lines are specifically around run_backtest)
# Wait, replace_file_content replaces the BLOCK. I should stick to replacing the Imports and the run_backtest function.
# I will make two calls. One for imports, one for the function.

# CALL 1: Imports



@router.get("/exchanges")
async def get_user_exchanges(current_user: dict = Depends(get_current_user)):
    """
    Obtiene los exchanges configurados del usuario
    """
    try:
        user = current_user
        user_id = user["openId"]
        
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
        logger.error(f"Error fetching exchanges for user {user.get('openId')}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markets/{exchange_id}")
async def get_exchange_markets(exchange_id: str):
    """
    Obtiene los tipos de mercado disponibles para un exchange
    
    Args:
        exchange_id: ID del exchange (ej: 'okx', 'binance')
    
    Returns:
        Lista de tipos de mercado disponibles
    """
    try:
        # Obtener mercados del exchange
        markets = await ccxt_service.get_markets(exchange_id)
        
        logger.info(f"Found {len(markets)} markets for exchange {exchange_id}")
        return {"markets": markets}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching markets for {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/{exchange_id}")
async def get_exchange_symbols(
    exchange_id: str, 
    market_type: Optional[str] = "spot"
):
    """
    Obtiene los símbolos con datos de precio para un exchange y tipo de mercado
    
    Args:
        exchange_id: ID del exchange
        market_type: Tipo de mercado (spot, future, swap, etc.)
    
    Returns:
        Lista de símbolos con precio actual y cambio porcentual
    """
    try:
        # Obtener símbolos con tickers
        symbols = await ccxt_service.get_symbols_with_tickers(exchange_id, market_type)
        
        logger.info(f"Found {len(symbols)} symbols for {exchange_id} ({market_type})")
        return {"symbols": symbols}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching symbols for {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_backtest(
    symbol: str,
    exchange_id: str = "okx",
    days: int = 7,
    timeframe: str = "1h",
    market_type: str = "spot",
    use_ai: bool = True,
    strategy: str = "auto",
    model_id: Optional[str] = None,
    initial_balance: float = 10000.0,
    trade_amount: Optional[float] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Ejecuta un backtest (Auth via JWT).
    """
    try:
        user = current_user
        user_id = user["openId"]

        
        # Obtener configuración del usuario si se usa IA
        user_config = None
        if use_ai:
            config = await db.app_configs.find_one({"userId": user["_id"]})
            if not config:
                raise HTTPException(
                    status_code=400, 
                    detail="User configuration not found. Please configure AI settings first."
                )
            
            # Validar que tenga al menos una API key configurada
            ai_provider = config.get("aiProvider", "gemini")
            key_map = {
                "gemini": "geminiApiKey",
                "openai": "openaiApiKey",
                "perplexity": "perplexityApiKey",
                "grok": "grokApiKey",
                "groq": "groqApiKey"
            }
            
            has_key = False
            for provider, key_field in key_map.items():
                if config.get(key_field):
                    has_key = True
                    break
            
            # Check ai_agents collection if no keys found in app_config
            if not has_key:
                active_agent = await db.ai_agents.find_one({"userId": user["_id"], "isActive": True})
                if active_agent:
                    has_key = True

            if not has_key:
                raise HTTPException(
                    status_code=400,
                    detail=f"No AI API keys configured. Please add at least one AI provider API key in settings."
                )
            
            user_config = config
        
        # Importar y ejecutar el servicio de backtest
        from api.src.application.services.backtest_service import BacktestService
        
        backtest_service = BacktestService(exchange_adapter=ccxt_service)
        results = await backtest_service.run_backtest(
            symbol=symbol,
            days=days,
            timeframe=timeframe,
            market_type=market_type,
            use_ai=use_ai,
            user_config=user_config,
            strategy=strategy,
            user_id=user_id,
            exchange_id=exchange_id,
            model_id=model_id,
            initial_balance=initial_balance,
            trade_amount=trade_amount
        )
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize", response_model=StrategyOptimizationResponse)
async def optimize_strategy(
    req: StrategyOptimizeRunRequest,
    current_user: dict = Depends(get_current_user)
):
    """Optimize a strategy's source code using AI.

    - Runs a single-strategy backtest to gather metrics/trades (keeps .pkl behavior intact).
    - Sends OHLCV + trades summary + current code to the AI.
    - Saves the optimized strategy under: strategiesOpt/<market>/<strategy>_opt.py
    """
    try:
        user = current_user
        user_id = user["openId"]

        # Load user's AI config (provider + keys)
        config = await db.app_configs.find_one({"userId": user["_id"]}) or {}

        # Run a single-strategy backtest to produce trades/metrics (use_ai=False here; AI is separate)
        from api.src.application.services.backtest_service import BacktestService
        backtest_service = BacktestService(exchange_adapter=ccxt_service)

        details = await backtest_service.run_backtest(
            symbol=req.symbol,
            days=req.days,
            timeframe=req.timeframe,
            market_type=req.market_type,
            use_ai=False,
            user_config=None,
            strategy=req.strategy_name,
            user_id=user_id,
            exchange_id=req.exchange_id,
            model_id=None,
            initial_balance=req.initial_balance,
            trade_amount=req.trade_amount,
        )

        # Load original strategy source code from repository
        market = (req.market_type or "spot").lower()
        strategy_name = req.strategy_name
        # strict path: api/src/domain/strategies/<market>/<strategy>.py
        src_path = os.path.normpath(os.path.join("api", "src", "domain", "strategies", market, f"{strategy_name}.py"))
        if not os.path.exists(src_path):
            raise HTTPException(status_code=404, detail=f"Strategy source not found: {src_path}")

        with open(src_path, "r", encoding="utf-8") as f:
            source_code = f.read()

        # Build basic trades summary
        trades = details.get("trades") or []
        pnls = [t.get("pnl") for t in trades if isinstance(t, dict) and t.get("pnl") is not None]
        pnls_num = [float(x) for x in pnls if isinstance(x, (int, float, str)) and str(x) not in ("nan", "None")]
        worst = sorted(pnls_num)[:5]
        best = sorted(pnls_num, reverse=True)[:5]

        trades_summary = {
            "worst_losses": worst,
            "best_wins": best,
        }

        metrics = details.get("metrics") or {
            "win_rate": details.get("win_rate"),
            "profit_pct": details.get("profit_pct"),
            "total_trades": details.get("total_trades"),
            "max_drawdown": (details.get("metrics") or {}).get("max_drawdown"),
        }

        # Call AI optimizer
        ai_service = AIService()
        opt = await ai_service.optimize_strategy_code(
            source_code=source_code,
            metrics=metrics,
            trades_summary=trades_summary,
            config=config,
            feedback=req.user_feedback,
        )

        optimized_code = (opt.get("code") or source_code)

        # Persist optimized code
        # Save under api/src/domain/strategiesopt/<market>/<strategy>_opt.py
        out_dir = os.path.normpath(os.path.join("api", "src", "domain", "strategiesopt", market))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{strategy_name}_opt.py")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(optimized_code)

        def _to_float(x):
            try:
                if x is None:
                    return None
                return float(x)
            except Exception:
                return None

        return StrategyOptimizationResponse(
            original_code=source_code,
            optimized_code=optimized_code,
            analysis=str(opt.get("analysis") or ""),
            modifications=list(opt.get("modifications") or []),
            expected_profit_pct=_to_float(opt.get("expected_profit_pct")),
            expected_win_rate=_to_float(opt.get("expected_win_rate")),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error optimizing strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deploy_bot")
async def deploy_bot(
    symbol: str,
    strategy: str,
    timeframe: str = "1h",
    initial_balance: float = 1000.0,
    leverage: int = 1,
    current_user: dict = Depends(get_current_user)
):
    """
    Crea un bot basado en una estrategia ganadora del backtest.
    Hereda el modo (Real/Simulado) de la configuración del usuario.
    """
    try:
        # Verificar usuario
        user = current_user
        user_id = user["openId"]
        
        # Obtener configuración para determinar Modo
        config = await db.app_configs.find_one({"userId": user["_id"]}) or {}
        # Por defecto "simulated" si no existe config o flag
        current_mode = "real" if config.get("tradingMode") == "live" else "simulated"
        
        # TODO: Si es FULL REAL, validar API Keys aquí antes de guardar

        # Crear BotInstance
        new_bot = BotInstance(
            id=None,
            user_id=user_id, # Usamos openId como identificador consistente en routers
            name=f"{strategy} - {symbol} ({current_mode})",
            symbol=symbol,
            strategy_name=strategy,
            timeframe=timeframe,
            mode=current_mode,
            status="active",
            config={
                "initial_balance": initial_balance,
                "leverage": leverage,
                "deployed_at": datetime.utcnow().isoformat()
            }
        )
        
        repo = MongoBotRepository()
        bot_id = await repo.save(new_bot)
        
        logger.info(f"Bot deployed: {bot_id} (Mode: {current_mode}) for {user_id}")
        
        return {
            "status": "success", 
            "message": f"Bot deployed for {symbol} in {current_mode} mode.",
            "bot_id": bot_id,
            "mode": current_mode
        }
        
    except Exception as e:
        logger.error(f"Error deploying bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml_models")
async def get_ml_models(market: str = "spot"):
    """
    Obtiene la lista de modelos ML entrenados disponibles
    
    Returns:
        Lista de modelos con sus metadatos (símbolo, accuracy, última fecha de entrenamiento)
    """
    try:
        from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
        ml_service = MLService(exchange_adapter=ccxt_service)
        models = await ml_service.get_models_status(market_type=market)
        
        logger.info(f"Found {len(models)} trained ML models")
        return {"models": models}
        
    except Exception as e:
        logger.error(f"Error fetching ML models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/virtual_balance")
async def get_virtual_balance(
    market_type: str = "CEX",
    asset: str = "USDT",
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene el balance virtual del usuario para backtesting
    
    Args:
        market_type: Tipo de mercado (CEX/DEX)
        asset: Asset del balance (USDT, BTC, etc.)
    
    Returns:
        Balance virtual del usuario
    """
    try:
        # Usuario
        user = current_user
        user_id = user["openId"]
        
        # Buscar balance virtual
        balance_doc = await db.virtual_balances.find_one({
            "userId": user["_id"],
            "marketType": market_type,
            "asset": asset
        })
        
        if balance_doc:
            balance = float(balance_doc.get("amount", 10000.0))
        else:
            # Balance por defecto si no existe
            balance = 10000.0
            logger.warning(f"No virtual balance found for {user_id}, using default: {balance}")
        
        return {
            "userId": user_id,
            "marketType": market_type,
            "asset": asset,
            "balance": balance
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching virtual balance for {current_user.get('openId')}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/optimize", response_model=StrategyOptimizationResponse)
async def optimize_strategy(
    request: StrategyOptimizationRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Recibe métricas y trades de un backtest reciente y utiliza IA para
    refactorizar el código de la estrategia y mejorar sus resultados.
    """
    try:
        user = current_user
        user_id = user["openId"]

        from api.src.application.services.backtest_service import BacktestService
        from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

        service = BacktestService(exchange_adapter=ccxt_service)

        result = await service.optimize_strategy(
            strategy_name=request.strategy_name,
            market_type=request.market_type,
            metrics=request.metrics,
            trades=request.trades,
            user_id=user_id,
            feedback=request.user_feedback
        )

        return result

    except Exception as e:
        logger.error(f"Error optimizing strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/strategies/save")
async def save_strategy_endpoint(
    request: SaveStrategyRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Guarda el código de una estrategia optimizada.
    """
    try:
        # TODO: Add specific permission checks if needed

        from api.src.application.services.backtest_service import BacktestService
        from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

        service = BacktestService(exchange_adapter=ccxt_service)

        result = await service.save_strategy(
            strategy_name=request.strategy_name,
            code=request.code,
            market_type=request.market_type
        )

        return result

    except Exception as e:
        logger.error(f"Error saving strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))
