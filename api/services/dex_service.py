import httpx
import logging
from typing import Optional, Dict, Any
from api.models.schemas import AnalysisResult, ExecutionResult
from api.models.mongodb import get_app_config, save_trade, update_virtual_balance

logger = logging.getLogger(__name__)

class DEXService:
    def __init__(self):
        self.base_url = "https://gmgn.ai"

    async def execute_trade(self, analysis: AnalysisResult, user_id: str = "default_user") -> ExecutionResult:
        config = await get_app_config(user_id)
        demo_mode = config.get("demoMode", True) if config else True
        
        # Obtener configuración DEX y límites
        dex_config = config.get("dexConfig", {}) if config else {}
        gmgn_api_key = config.get("gmgnApiKey") if config else None
        max_amount = 1.0 # Default SOL
        if config and "investmentLimits" in config:
            max_amount = config["investmentLimits"].get("dexMaxAmount", 1.0)

        symbol = analysis.symbol
        side = analysis.decision.upper()
        
        # Usar el monto sugerido o el máximo permitido
        suggested_amount = analysis.parameters.get('amount', 0) if analysis.parameters else 0
        amount = min(suggested_amount, max_amount) if suggested_amount > 0 else max_amount

        if demo_mode:
            logger.info(f"[MODO DEMO DEX] Simulando {side} para {symbol} con monto {amount}")
            
            # Registrar trade demo en MongoDB
            trade_doc = {
                "userId": config["userId"] if config else None,
                "symbol": symbol,
                "side": side,
                "price": 0.0, # Precio simulado
                "amount": amount,
                "marketType": "DEX",
                "isDemo": True,
                "status": "completed"
            }
            await save_trade(trade_doc)
            
            # Actualizar balance virtual de SOL (simplificado)
            # await update_virtual_balance(user_id, "DEX", "SOL", new_amount)
            
            return ExecutionResult(
                success=True,
                message=f"MODO DEMO DEX: {side} {symbol} registrado (Límite: {max_amount})"
            )

        if not gmgn_api_key or not dex_config.get("walletPrivateKey"):
            return ExecutionResult(success=False, message="Credenciales DEX (GMGN API o Private Key) no configuradas")

        try:
            network = analysis.parameters.get('network', 'solana') if analysis.parameters else 'solana'
            logger.info(f"Iniciando operación DEX REAL en {network} para {symbol} con monto {amount}")
            # Lógica de integración con GMGN.ai o similar
            return ExecutionResult(success=True, message=f"Operación DEX real enviada (Simulado). Monto: {amount}")

        except Exception as e:
            logger.error(f"Error ejecutando trade en DEX: {e}")
            return ExecutionResult(success=False, message=f"Error en DEX: {str(e)}")
