import logging
from api.core.ports.ai_port import AIPort
from api.core.domain.signal import RawSignal, SignalAnalysis, Decision

logger = logging.getLogger(__name__)

class ProcessSignalUseCase:
    def __init__(self, ai_port: AIPort):
        self.ai_port = ai_port

    async def execute(self, raw_signal: RawSignal, user_config: dict) -> SignalAnalysis:
        logger.info(f"Processing signal from {raw_signal.source}")
        
        # 1. Analizar la señal con IA
        analysis = await self.ai_port.analyze_signal(raw_signal, user_config)
        
        # 2. Lógica de negocio adicional (ej. validaciones de seguridad extra)
        if analysis.decision != Decision.HOLD:
            if not analysis.is_safe:
                logger.warning(f"Signal for {analysis.symbol} marked as unsafe")
            else:
                logger.info(f"Signal for {analysis.symbol} approved with confidence {analysis.confidence}")
        
        return analysis
