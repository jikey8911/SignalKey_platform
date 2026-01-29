"""
Endpoints para backtesting - Exchanges, Markets y Symbols
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime
from api.src.adapters.driven.persistence.mongodb import db
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
from api.src.application.services.ml_service import MLService

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
    user_id: str,
    symbol: str,
    exchange_id: str = "binance",
    days: int = 7,
    timeframe: str = "1h",
    use_ai: bool = True, # Default to True for ML backtest
    strategy: str = "auto", # Default to auto/neural
    model_id: Optional[str] = None # Received from frontend
):
    """
    Ejecuta un backtest con estrategia SMA o con IA
    
    Args:
        user_id: ID del usuario (openId)
        symbol: Símbolo a analizar (ej: BTC/USDT)
        exchange_id: ID del exchange (por defecto binance)
        days: Número de días históricos
        timeframe: Timeframe de las velas
        use_ai: Si True, usa IA; si False, usa estrategia SMA
        strategy: Estrategia de IA ("standard" o "sniper") si use_ai=True
    
    Returns:
        Resultados del backtest con métricas
    """
    try:
        # Verificar que el usuario existe
        user = await db.users.find_one({"openId": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
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
                "grok": "grokApiKey"
            }
            
            has_key = False
            for provider, key_field in key_map.items():
                if config.get(key_field):
                    has_key = True
                    break
            
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
            use_ai=use_ai,
            user_config=user_config,
            strategy=strategy,
            user_id=user_id,
            exchange_id=exchange_id,
            model_id=model_id
        )
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deploy_bot")
async def deploy_bot(
    user_id: str,
    symbol: str,
    strategy: str,
    initial_balance: float = 1000.0,
    leverage: int = 1
):
    """
    Crea un bot simulado basado en una estrategia ganadora del backtest.
    """
    try:
        # Verificar usuario
        user = await db.users.find_one({"openId": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Crear configuración del bot
        # En el futuro esto podría usar un servicio dedicado
        bot_config = {
            "userId": user["_id"],
            "symbol": symbol,
            "strategy": strategy,
            "status": "active",  # O "simulated"
            "mode": "simulation", # Explicitamente simulado
            "initialBalance": initial_balance,
            "currentBalance": initial_balance,
            "leverage": leverage,
            "pnl": 0.0,
            "trades": [],
            "createdAt": datetime.utcnow(),
            "lastCheck": datetime.utcnow()
        }
        
        # Insertar en colección 'bots' (o trades si no existe bots)
        # Asumiremos 'trades' por ahora ya que es lo que vimos en el código
        # pero con un flag especial o en una colección nueva si preferimos.
        # El usuario pidió "crear el bot", así que lo guardamos.
        
        # Como no vi modelo de Bot explícito, lo guardaré en 'active_bots' o similar si existe,
        # si no, lo guardamos en 'trades' con status 'active_bot'.
        
        # Revisando db usage en otros archivos, parece que usan 'trades' para todo?
        # Mejor creamos una colección 'bots' si no existe.
        
        result = await db.bots.insert_one(bot_config)
        
        return {
            "status": "success", 
            "message": f"Bot deployed for {symbol} with strategy {strategy}",
            "bot_id": str(result.inserted_id)
        }
        
    except Exception as e:
        logger.error(f"Error deploying bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml_models")
async def get_ml_models():
    """
    Obtiene la lista de modelos ML entrenados disponibles
    
    Returns:
        Lista de modelos con sus metadatos (símbolo, accuracy, última fecha de entrenamiento)
    """
    try:
        ml_service = MLService()
        models = await ml_service.get_models_status()
        
        logger.info(f"Found {len(models)} trained ML models")
        return {"models": models}
        
    except Exception as e:
        logger.error(f"Error fetching ML models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/virtual_balance/{user_id}")
async def get_virtual_balance(
    user_id: str,
    market_type: str = "CEX",
    asset: str = "USDT"
):
    """
    Obtiene el balance virtual del usuario para backtesting
    
    Args:
        user_id: ID del usuario (openId)
        market_type: Tipo de mercado (CEX/DEX)
        asset: Asset del balance (USDT, BTC, etc.)
    
    Returns:
        Balance virtual del usuario
    """
    try:
        # Buscar usuario
        user = await db.users.find_one({"openId": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
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
        logger.error(f"Error fetching virtual balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

