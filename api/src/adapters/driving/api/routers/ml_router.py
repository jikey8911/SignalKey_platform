from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from api.src.application.services.ml_service import MLService
from api.src.application.services.cex_service import CEXService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ml", tags=["ml"])

# Inyección de dependencia correcta
ml_service = MLService(exchange_adapter=CEXService())

class TrainRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    days: int = 365
    epochs: int = 20
    user_id: str = "default_user"
    exchange: str = "binance"
    market: str = "spot"

class BatchTrainRequest(BaseModel):
    symbols: list[str]
    timeframe: str = "1h"
    days: int = 365
    epochs: int = 20
    user_id: str = "default_user"
    exchange: str = "binance"
    market: str = "spot"

class PredictRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    candles: list[dict] # [ {'timestamp':..., 'open':..., 'close':...}, ... ]

@router.post("/train")
async def train_all_strategies_endpoint(request: BatchTrainRequest, background_tasks: BackgroundTasks):
    """
    Entrena TODOS los modelos de estrategia (RandomForest) utilizando los símbolos provistos.
    Nueva arquitectura agnóstica.
    """
    try:
        logging.info(f"🚀 Endpoint /train called. Request User ID: {request.user_id}")
        
        # Resolve dependencies inside endpoint to ensure correct context
        # Ideally use FastAPI depends, but for now we create fresh instances or import from main if possible.
        # However, to avoid circular imports with main, we use fresh instantiation but configured correctly.
        from api.main import ccxt_adapter, cex_service 
        # But importing from api.main inside router might be cyclic if main imports routers.
        # Fallback: Create generic instances. Since user_id is passed, logical flow works.
        logging.info(f"🔧 Initializing MLService for User: {request.user_id}")
        service = MLService(exchange_adapter=CEXService(ccxt_adapter=ccxt_adapter))
        
        background_tasks.add_task(
            service.train_all_strategies, 
            request.symbols, 
            request.timeframe, 
            request.days,
            request.user_id
        )
        logging.info(f"✅ Background task added for User: {request.user_id} - Symbols: {request.symbols}")
        return {"status": "started", "message": f"Training started for {len(request.symbols)} symbols"}
    except Exception as e:
        logger.error(f"❌ Error starting training endpoint: {e}")
        # Try generic fallback if import fails
        service = MLService(exchange_adapter=CEXService())
        background_tasks.add_task(
            service.train_all_strategies, 
            request.symbols, 
            request.timeframe, 
            request.days,
            request.user_id
        )
        return {"status": "started (fallback)", "message": f"Training started (fallback)"}

@router.get("/models")
async def get_models():
    """Retorna la lista de estrategias/modelos disponibles"""
    # Use generic service for models list
    models = await MLService(exchange_adapter=CEXService()).get_available_models()
    return [{"id": m, "status": "Ready", "type": "RandomForest"} for m in models]

@router.post("/train-selector")
async def train_selector(request: BatchTrainRequest, background_tasks: BackgroundTasks):
    """
    Entrena el Modelo Selector (Meta-Learning) de forma manual e independiente.
    Este modelo aprende a elegir la mejor estrategia basándose en condiciones de mercado.
    """
    try:
        from api.main import ccxt_adapter
        service = MLService(exchange_adapter=CEXService(ccxt_adapter=ccxt_adapter))
        
        background_tasks.add_task(
            service.train_selector_model,
            request.symbols,
            request.timeframe,
            request.days,
            request.user_id
        )
        return {
            "status": "started", 
            "message": f"Selector training started using {len(request.symbols)} symbols."
        }
    except Exception as e:
        logger.error(f"Error starting selector training: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/predict")
async def predict_strategy(request: PredictRequest):
    """
    Inferencia Real-Time: Usa el StrategyTrainer para dar señales basadas en el momento actual.
    """
    try:
        # Re-verify candles are mostly valid
        if not request.candles or len(request.candles) < 50:
             # Necesitamos historial para que los indicadores funcionen
             logger.warning(f"Predict request with few candles ({len(request.candles)}). Indicators might fail.")
        
        # Predict uses local models, no exchange call needed really, but service needs init
        service = MLService(exchange_adapter=CEXService())
        result = service.predict(request.symbol, request.timeframe, request.candles)
        return result
    except Exception as e:
        logger.error(f"Error predicting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Deprecated/Mapped Endpoints for compatibility
@router.post("/train_global")
async def train_global_redirect(request: BatchTrainRequest, background_tasks: BackgroundTasks):
    return await train_all_strategies_endpoint(request, background_tasks)

@router.post("/train-strategies")
async def train_strategies_redirect(request: BatchTrainRequest, background_tasks: BackgroundTasks):
    return await train_all_strategies_endpoint(request, background_tasks)
