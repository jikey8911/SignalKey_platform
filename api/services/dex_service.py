import httpx
import logging
from crypto_bot_api.config import Config
from crypto_bot_api.models.schemas import AnalysisResult, ExecutionResult

logger = logging.getLogger(__name__)

class DEXService:
    def __init__(self):
        self.api_key = Config.GMGN_API_KEY
        self.base_url = "https://gmgn.ai"
        self.wallet_private_key = Config.DEX_WALLET_PRIVATE_KEY

    async def execute_trade(self, analysis: AnalysisResult) -> ExecutionResult:
        if Config.DEMO_MODE:
            from crypto_bot_api.models.database import SessionLocal, VirtualBalance, TradeHistory
            db = SessionLocal()
            
            symbol = analysis.symbol
            side = analysis.decision.upper()
            amount = analysis.parameters.get('amount', 0.1) if analysis.parameters else 0.1
            
            logger.info(f"[MODO DEMO DEX] Simulando {side} para {symbol}")
            
            # Registrar trade demo
            new_trade = TradeHistory(
                symbol=symbol, side=side, price=0.0, # Precio no disponible fácilmente en simulación DEX sin API
                amount=amount, market_type="DEX", is_demo=True
            )
            db.add(new_trade)
            
            # Actualizar balance virtual de SOL
            balance = db.query(VirtualBalance).filter_by(market_type="DEX", asset="SOL").first()
            if side == "BUY":
                balance.amount -= amount
            else:
                balance.amount += amount
                
            db.commit()
            db.close()
            
            return ExecutionResult(
                success=True,
                message=f"MODO DEMO DEX: {side} {symbol} registrado en balance virtual"
            )

        if not self.api_key or not self.wallet_private_key:
            return ExecutionResult(success=False, message="Credenciales DEX no configuradas")

        try:
            symbol = analysis.symbol
            network = analysis.parameters.get('network', 'solana') if analysis.parameters else 'solana'
            logger.info(f"Iniciando operación DEX REAL en {network} para {symbol}")
            return ExecutionResult(success=True, message="Operación DEX real enviada (Simulado)")

        except Exception as e:
            logger.error(f"Error ejecutando trade en DEX: {e}")
            return ExecutionResult(success=False, message=f"Error en DEX: {str(e)}")
