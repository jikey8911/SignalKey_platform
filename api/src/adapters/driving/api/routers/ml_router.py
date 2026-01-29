from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from api.src.application.services.ml_service import MLService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ml", tags=["ml"])
ml_service = MLService()

class TrainRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    days: int = 365
    epochs: int = 20
    user_id: str = "default_user"
    exchange_id: str = None

class BatchTrainRequest(BaseModel):
    symbols: list[str]
    timeframe: str = "1h"
    days: int = 365
    epochs: int = 20
    user_id: str = "default_user"
    exchange_id: str = None

@router.post("/train")
async def train_model(request: TrainRequest, background_tasks: BackgroundTasks):
    """
    Inicia el entrenamiento de un modelo en segundo plano.
    """
    try:
        background_tasks.add_task(
            ml_service.train_model, 
            request.symbol, 
            request.timeframe, 
            request.days, 
            request.epochs,
            request.user_id,
            request.exchange_id
        )
        return {"status": "started", "message": f"Training started for {request.symbol}"}
    except Exception as e:
        logger.error(f"Error starting training: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/train_batch")
async def train_batch(request: BatchTrainRequest, background_tasks: BackgroundTasks):
    """
    Inicia el entrenamiento masivo para una lista de símbolos.
    """
    try:
        for symbol in request.symbols:
            background_tasks.add_task(
                ml_service.train_model, 
                symbol, 
                request.timeframe, 
                request.days, 
                request.epochs,
                request.user_id,
                request.exchange_id
            )
        return {
            "status": "batch_started", 
            "message": f"Queued training for {len(request.symbols)} symbols: {', '.join(request.symbols)}"
        }
    except Exception as e:
        logger.error(f"Error starting batch training: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/train_global")
async def train_global(request: BatchTrainRequest, background_tasks: BackgroundTasks):
    """
    Entrena un ÚNICO modelo GLOBAL combinando datos de todos los símbolos proporcionados.
    """
    try:
        background_tasks.add_task(
            ml_service.train_global_model,
            request.symbols,
            request.timeframe,
            request.days,
            request.epochs,
            request.user_id,
            request.exchange_id
        )
        return {
            "status": "global_training_started",
            "message": f"Started Global Model training using {len(request.symbols)} symbols."
        }
    except Exception as e:
        logger.error(f"Error starting global training: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models")
async def get_models():
    """Retorna la lista de modelos entrenados y su estado"""
    return await ml_service.get_models_status()

class PredictRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    candles: list[dict] # [ {'timestamp':..., 'open':..., 'close':...}, ... ]

@router.post("/predict")
async def predict_strategy(request: PredictRequest):
    """
    Usa el Meta-Selector para decidir la mejor estrategia y ejecutarla.
    """
    try:
        result = ml_service.predict(request.symbol, request.timeframe, request.candles)
        return result
    except Exception as e:
        logger.error(f"Error predicting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/train-strategies")
async def train_strategies(request: BatchTrainRequest, background_tasks: BackgroundTasks):
    """
    Entrena modelos agnósticos (Random Forest) para cada estrategia disponible.
    Usa datos de los símbolos proporcionados para aprender patrones generales.
    """
    try:
        # Default to True for random dates as per requirement "soporte de fechas aleatorias"
        # Since BatchTrainRequest doesn't have use_random_date field yet, we default to True or assume logic handles it.
        # Ideally we update BatchTrainRequest, but user didn't ask to change the model explicitly, just "Update ml_router".
        # I'll rely on defaults or hardcode True for this specific endpoint effectively fulfilling the requirement.
        
        background_tasks.add_task(
            ml_service.train_agnostic_strategies,
            request.symbols,
            request.timeframe,
            request.days,
            request.user_id,
            request.exchange_id,
            True # use_random_date=True forced for this endpoint to meet Sprint 1 req
        )
        return {
            "status": "started",
            "message": f"Started Agnostic Strategy Training using {len(request.symbols)} symbols."
        }
    except Exception as e:
        logger.error(f"Error starting strategy training: {e}")
        raise HTTPException(status_code=500, detail=str(e))
