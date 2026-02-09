from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
from api.src.adapters.driven.persistence.mongodb import db, get_app_config
from api.src.infrastructure.security.auth_deps import get_current_user
from api.src.domain.entities.signal import SignalStatus, Decision, MarketType
from api.src.domain.models.schemas import AnalysisResult
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
    # Use ObjectId directly
    user_id_obj = current_user["_id"]
    
    # Update repository method to accept ObjectId (or ensure it handles both)
    # The repository update is part of the next step, but here we pass the ID.
    # We will pass the string representation for now, assuming repo handles conversion or uses strings if legacy.
    # However, the repo is MongoDBSignalRepository and we will update it to expect ObjectId.
    # Let's pass the string representation of ObjectId to maintain compatibility with `find_by_user` which we will update.
    signals = await signal_repo.find_by_user(str(user_id_obj))
    
    # Serializar a dicts usando el método helper de la entidad
    return [s.to_dict() for s in signals[:limit]]

@router.get("/bot/{bot_id}")
async def list_bot_signals(
    bot_id: str,
    current_user: dict = Depends(get_current_user),
    signal_repo: MongoDBSignalRepository = Depends(get_signal_repository),
    limit: int = 50
):
    """
    Lista las señales específicas de un bot (Instancia de estrategia).
    """
    # Verificación de propiedad del bot (opcional pero recomendado)
    # Por ahora asumimos que si tiene el ID puede verlo, o filtramos después.
    # Idealmente verificaríamos que el bot pertenece al usuario.
    
    signals = await signal_repo.find_by_bot_id(bot_id)
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
    user_id_obj = current_user["_id"]
    signal = await signal_repo.find_by_id(signal_id)
    
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
        
    # Check ownership using string comparison of ObjectIds
    if str(signal.userId) != str(user_id_obj):
        raise HTTPException(status_code=403, detail="Not authorized to approve this signal")

    # Re-ejecutar lógica de bot_service
    from api.main import signal_bot_service
    
    # Crear AnalysisResult (Schema Pydantic) a partir de la señal
    analysis = AnalysisResult(
        decision=signal.decision.value if hasattr(signal.decision, 'value') else str(signal.decision or "BUY"),
        symbol=signal.symbol or "UNKNOWN",
        market_type=signal.marketType.value if hasattr(signal.marketType, 'value') else str(signal.marketType or "CEX"),
        confidence=signal.confidence or 0.8,
        reasoning=f"Manual approval of signal {signal_id}. Original reasoning: {signal.reasoning}",
        is_safe=True,
        parameters=signal.parameters.to_dict() if signal.parameters else {}
    )
    
    config = await get_app_config(str(user_id_obj))
    
    try:
        # Pasamos signal_id para que se actualice el estado de la señal existente
        # Note: activate_bot likely expects userId as string? We pass str(ObjectId).
        result = await signal_bot_service.activate_bot(analysis, str(user_id_obj), config, signal_id=signal_id)

        if result.success:
            # El servicio ya actualiza la señal si se pasa signal_id, pero podemos asegurar estado
             await signal_repo.update(signal_id, {
                "status": SignalStatus.EXECUTING,
                "tradeId": result.details.get("botId") if result.details else None
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
