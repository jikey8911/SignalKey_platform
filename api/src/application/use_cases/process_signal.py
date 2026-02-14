from datetime import datetime
from typing import List, Dict, Any
import logging
from api.src.domain.entities.signal import Signal, SignalStatus, SignalAnalysis, Decision, Direction, RawSignal
from api.src.domain.ports.output.signal_repository import ISignalRepository
from api.src.domain.ports.output.ai_port import IAIPort
from api.src.domain.ports.output.notification_port import INotificationPort
from api.src.domain.ports.output.telegram_repository_port import ITelegramSignalRepository, ITelegramTradeRepository

logger = logging.getLogger(__name__)

class ProcessSignalUseCase:
    def __init__(
        self, 
        signal_repository: ISignalRepository, 
        ai_service: IAIPort,
        notification_service: INotificationPort,
        telegram_signal_repository: ITelegramSignalRepository,
        telegram_trade_repository: ITelegramTradeRepository,
        trade_service: Any # TelegramTradeService
    ):
        self.signal_repository = signal_repository
        self.ai_service = ai_service
        self.notification_service = notification_service
        self.telegram_signal_repository = telegram_signal_repository
        self.telegram_trade_repository = telegram_trade_repository
        self.trade_service = trade_service

    async def execute(self, raw_text: str, source: str, user_id: str, config: Dict[str, Any]) -> None:
        # 1. Registro inicial para auditoría
        signal = Signal(
            id=None,
            userId=user_id,
            source=source,
            rawText=raw_text,
            status=SignalStatus.PROCESSING,
            createdAt=datetime.utcnow()
        )
        saved_signal = await self.signal_repository.save(signal)
        
        await self._notify_frontend(user_id, "signal_new", {
            "id": saved_signal.id,
            "source": source,
            "status": saved_signal.status,
            "createdAt": saved_signal.createdAt.isoformat() + "Z"
        })

        # Validación rápida de configuración
        if not config.get("isAutoEnabled", True) and not config.get("botTelegramActivate", False):
            await self._cancel_signal(saved_signal.id, "Auto-processing disabled by user")
            return

        try:
            # 2. Análisis con IA (Gemini)
            analyses = await self.ai_service.analyze_signal(raw_text, config)
            
            for i, analysis in enumerate(analyses):
                current_id = await self._get_signal_id(saved_signal, i, user_id, source, raw_text)

                # 3. FILTRO DE SEGURIDAD: Evitar duplicados activos (Puerto/Adapter)
                if await self._is_trade_already_open(user_id, analysis.symbol):
                    logger.info(f"🚫 Señal duplicada omitida: {analysis.symbol} para usuario {user_id}")
                    await self.signal_repository.update(current_id, {
                        "status": SignalStatus.REJECTED,
                        "executionMessage": f"Duplicate trade: {analysis.symbol} already has an active operation."
                    })
                    continue

                # Determinar estatus y actualizar
                status = SignalStatus.ACCEPTED if analysis.decision == Decision.APPROVED else SignalStatus.REJECTED
                update_data = self._prepare_update_data(analysis, status)
                await self.signal_repository.update(current_id, update_data)

                if status == SignalStatus.ACCEPTED:
                    # Guardar en colección específica de Telegram para histórico/estadísticas (aprobada o rechazada)
                    chat_id = source.replace("telegram_", "", 1) if isinstance(source, str) and source.startswith("telegram_") else None
                    telegram_signal_doc = {
                        "signalId": current_id,
                        "userId": user_id,
                        "source": source,
                        "chatId": chat_id,
                        "status": str(status),
                        "analysis": update_data,
                        "timestamp": datetime.utcnow(),
                    }
                    await self.telegram_signal_repository.save_signal(telegram_signal_doc)

                    if analysis.decision == Decision.REJECTED or analysis.direction == Direction.HOLD:
                        continue

                    # 4. PASO CRÍTICO: Crear el Trade y activar el flujo de SignalKey
                    if analysis.is_safe:
                        # Usar el servicio de trades inyectado
                        result = await self.trade_service.create_telegram_trade(analysis, user_id, config, signal_id=current_id)
                        
                        final_status = SignalStatus.EXECUTING if result.success else SignalStatus.FAILED
                        await self.signal_repository.update(current_id, {
                            "status": final_status,
                            "tradeId": result.details.get("tradeId") if result.success else None,
                            "executionMessage": None if result.success else result.message
                        })
                    else:
                        await self.signal_repository.update(current_id, {
                            "status": SignalStatus.REJECTED_UNSAFE,
                            "riskScore": getattr(analysis, 'risk_score', None)
                        })

                # Notificar progreso al frontend
                await self._notify_frontend(user_id, "signal_update", {
                    "id": current_id, 
                    "symbol": analysis.symbol,
                    **update_data,
                    "createdAt": datetime.utcnow().isoformat() + "Z"
                })

        except Exception as e:
            logger.error(f"❌ Error en ProcessSignalUseCase: {e}", exc_info=True)
            await self.signal_repository.update(saved_signal.id, {
                "status": SignalStatus.FAILED, 
                "executionMessage": str(e)
            })

    async def _get_signal_id(self, base_signal: Signal, index: int, user_id: str, source: str, raw_text: str) -> str:
        if index == 0:
            return base_signal.id
        
        # Para señales múltiples en un mismo mensaje, creamos registros adicionales
        new_sig = Signal(
            id=None,
            userId=user_id,
            source=source,
            rawText=raw_text,
            status=SignalStatus.PROCESSING,
            createdAt=datetime.utcnow()
        )
        saved = await self.signal_repository.save(new_sig)
        return saved.id

    async def _is_trade_already_open(self, user_id: str, symbol: str) -> bool:
        """Verifica si ya hay un trade activo o esperando para este símbolo usando el puerto."""
        return await self.telegram_trade_repository.has_active_trade(user_id, symbol)

    def _prepare_update_data(self, analysis: SignalAnalysis, status: SignalStatus) -> Dict[str, Any]:
        return {
            "decision": analysis.decision.value,
            "symbol": analysis.symbol,
            "direction": analysis.direction.value,
            "status": status,
            "marketType": analysis.market_type.value,
            "reasoning": analysis.reasoning,
            "parameters": analysis.parameters.to_dict() if hasattr(analysis.parameters, 'to_dict') else analysis.parameters,
            "confidence": analysis.confidence
        }

    async def _notify_frontend(self, user_id: str, event: str, data: Any):
        await self.notification_service.emit_to_user(user_id, event, data)

    async def _cancel_signal(self, signal_id: str, message: str):
        await self.signal_repository.update(signal_id, {
            "status": SignalStatus.CANCELLED,
            "executionMessage": message
        })
