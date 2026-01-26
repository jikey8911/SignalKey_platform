from datetime import datetime
from typing import List, Dict, Any
from src.domain.models.signal import Signal, SignalStatus, SignalAnalysis, Decision
from src.domain.ports.output.signal_repository import ISignalRepository
from src.domain.ports.output.ai_port import AIPort
from src.domain.ports.output.notification_port import INotificationPort
from src.domain.exceptions.infrastructure_exceptions import InfrastructureServiceError

class ProcessSignalUseCase:
    def __init__(
        self, 
        signal_repository: ISignalRepository, 
        ai_service: AIPort,
        notification_service: INotificationPort,
        bot_service: Any # Simplificado para este ejemplo
    ):
        self.signal_repository = signal_repository
        self.ai_service = ai_service
        self.notification_service = notification_service
        self.bot_service = bot_service

    async def execute(self, raw_text: str, source: str, user_id: str, config: Dict[str, Any]) -> None:
        # 1. Crear registro inicial
        signal = Signal(
            id=None,
            userId=user_id,
            source=source,
            rawText=raw_text,
            status=SignalStatus.PROCESSING,
            createdAt=datetime.utcnow()
        )
        
        saved_signal = await self.signal_repository.save(signal)
        
        # Notificar inicio
        await self.notification_service.emit_to_user(user_id, "signal_update", {
            "id": saved_signal.id,
            "source": source,
            "status": saved_signal.status,
            "createdAt": saved_signal.createdAt.isoformat()
        })

        if not config.get("isAutoEnabled", True):
            await self.signal_repository.update(saved_signal.id, {
                "status": SignalStatus.CANCELLED,
                "executionMessage": "Auto-processing disabled by user"
            })
            return

        # 2. Analizar con IA
        try:
            analyses = await self.ai_service.analyze_signal(raw_text, config)
            
            for i, analysis in enumerate(analyses):
                current_id = saved_signal.id
                if i > 0:
                    # Crear nueva señal para tokens adicionales
                    new_sig = Signal(
                        id=None,
                        userId=user_id,
                        source=source,
                        rawText=raw_text,
                        status=SignalStatus.PROCESSING,
                        createdAt=datetime.utcnow()
                    )
                    saved_new = await self.signal_repository.save(new_sig)
                    current_id = saved_new.id

                # Actualizar con análisis
                status = SignalStatus.ACCEPTED if analysis.decision != Decision.HOLD else SignalStatus.REJECTED
                update_data = {
                    "decision": analysis.decision,
                    "symbol": analysis.symbol,
                    "marketType": analysis.market_type,
                    "confidence": analysis.confidence,
                    "reasoning": analysis.reasoning,
                    "status": status
                }
                await self.signal_repository.update(current_id, update_data)
                
                await self.notification_service.emit_to_user(user_id, "signal_update", {
                    "id": current_id,
                    "symbol": analysis.symbol,
                    "status": status,
                    "decision": analysis.decision
                })

                if analysis.decision == Decision.HOLD:
                    continue

                # 3. Validar Seguridad
                if not analysis.is_safe:
                    await self.signal_repository.update(current_id, {
                        "status": SignalStatus.REJECTED_UNSAFE,
                        "riskScore": analysis.risk_score
                    })
                    continue

                # 4. Activar Bot (Simplificado)
                try:
                    result = await self.bot_service.activate_bot(analysis, user_id, config)
                    if result.success:
                        await self.signal_repository.update(current_id, {
                            "status": SignalStatus.EXECUTING,
                            "tradeId": result.details.get("botId")
                        })
                    else:
                        await self.signal_repository.update(current_id, {
                            "status": SignalStatus.REJECTED,
                            "executionMessage": result.message
                        })
                except Exception as e:
                    raise InfrastructureServiceError("BotService", e)

        except Exception as e:
            await self.signal_repository.update(saved_signal.id, {
                "status": SignalStatus.FAILED,
                "executionMessage": str(e)
            })
            raise InfrastructureServiceError("AIService", e)
