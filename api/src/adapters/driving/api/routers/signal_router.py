from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
from api.src.adapters.driven.persistence.mongodb import db, get_app_config
from api.src.infrastructure.security.auth_deps import get_current_user
from api.src.domain.models.signal import SignalStatus, Decision, SignalAnalysis, MarketType
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["Signals Management"])

def get_signal_repository():
    return MongoDBSignalRepository(db)

@router.get("/")
async def list_user_signals(
    current_user: dict = Depends(get_current_user),
    signal_repo: MongoDBSignalRepository = Depends(get_signal_repository),
    limit: int = 50
):
    """
    Lista las señales para el usuario actual.
    """
    user_id = current_user["openId"]
    
    # Use repository instead of direct DB access
    signals = await signal_repo.find_by_user(user_id)
    
    # Sort locally by createdAt descending
    signals.sort(key=lambda x: x.createdAt, reverse=True)
    
    return [s.to_dict() for s in signals[:limit]]

@router.post("/{signal_id}/approve")
async def approve_signal(
    signal_id: str,
    current_user: dict = Depends(get_current_user),
    signal_repo: MongoDBSignalRepository = Depends(get_signal_repository)
):
    """
    Aprueba y ejecuta una señal manualmente.
    """
    user_id = current_user["openId"]
    signal = await signal_repo.find_by_id(signal_id)
    
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
        
    if str(signal.userId) != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to approve this signal")

    # Re-ejecutar lógica de bot_service
    # Importación tardía para evitar ciclos con api.main
    from api.main import signal_bot_service
    
    # Crear análisis a partir de la señal
    analysis = SignalAnalysis(
        decision=signal.decision or Decision.BUY,
        symbol=signal.symbol or "UNKNOWN",
        market_type=signal.marketType or MarketType.SPOT,
        confidence=signal.confidence or 0.8,
        reasoning=f"Manual approval of signal {signal_id}. Original reasoning: {signal.reasoning}",
        is_safe=True
    )
    
    config = await get_app_config(user_id)
    
    try:
        result = await signal_bot_service.activate_bot(analysis, user_id, config)
        if result.success:
            await signal_repo.update(signal_id, {
                "status": SignalStatus.EXECUTING,
                "tradeId": result.details.get("botId")
            })
            return {"success": True, "message": "Signal approved and executed", "details": result.details}
        else:
            await signal_repo.update(signal_id, {
                "status": SignalStatus.FAILED,
                "executionMessage": result.message
            })
            return {"success": False, "message": result.message}
    except Exception as e:
        logger.error(f"Error approving signal {signal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
