from fastapi import APIRouter, HTTPException, Depends
from api.src.adapters.driven.persistence.mongodb import db
from api.src.infrastructure.ai.model_manager import ModelManager
import logging
from datetime import datetime

router = APIRouter(prefix="/health", tags=["System Observability"])
logger = logging.getLogger(__name__)

async def check_mongo():
    try:
        # Ping DB
        await db.db.command('ping')
        return "connected"
    except Exception as e:
        logger.error(f"Health Check Mongo Error: {e}")
        return "disconnected"

async def check_models():
    try:
        loaded = ModelManager().loaded_models
        count = len(loaded)
        if count == 0 and not ModelManager()._initialized:
             return "uninitialized"
        return f"{count} models loaded"
    except Exception:
        return "error"

@router.get("/")
async def health_check():
    """
    Retorna el estado de salud de los servicios críticos.
    Sprint 4: Observabilidad Full Stack.
    """
    mongo_status = await check_mongo()
    models_status = await check_models()
    
    # Global Services States (approximated, as we don't have global DI container fully accessible here without circular imports often)
    # We can infer some states or rely on mongo status as proxy for backend readiness.
    
    status = "healthy"
    if mongo_status != "connected":
        status = "degraded"
        
    return {
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": mongo_status,
            "ai_engine": models_status,
        },
        "version": "1.0.0-sprint4"
    }

@router.get("/deep")
async def deep_health_check():
    """
    Diagnóstico profundo (incluye latencia y checks más pesados).
    """
    start = datetime.now()
    mongo_status = await check_mongo()
    latency = (datetime.now() - start).total_seconds() * 1000
    
    return {
        "status": "ok" if mongo_status == "connected" else "error",
        "latency_ms": round(latency, 2),
        "details": {
            "mongo_connection": mongo_status
        }
    }
