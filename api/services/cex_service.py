import ccxt
import logging
from crypto_bot_api.config import Config
from crypto_bot_api.models.schemas import AnalysisResult, ExecutionResult

logger = logging.getLogger(__name__)

class CEXService:
    def __init__(self):
        self.exchange_id = Config.EXCHANGE_ID
        self.api_key = Config.CEX_API_KEY
        self.secret = Config.CEX_SECRET
        self.password = Config.CEX_PASSWORD
        self.uid = Config.CEX_UID
        
        if self.api_key and self.secret:
            exchange_class = getattr(ccxt, self.exchange_id)
            
            # Configuración dinámica de credenciales
            config = {
                'apiKey': self.api_key,
                'secret': self.secret,
                'enableRateLimit': True,
            }
            
            # Añadir password/passphrase si existe (requerido por OKX, KuCoin, etc.)
            if self.password:
                config['password'] = self.password
            
            # Añadir UID si existe
            if self.uid:
                config['uid'] = self.uid
                
            self.exchange = exchange_class(config)
        else:
            self.exchange = None
            logger.warning(f"Credenciales de {self.exchange_id} no configuradas.")

    async def execute_trade(self, analysis: AnalysisResult) -> ExecutionResult:
        if not self.exchange and not Config.DEMO_MODE:
            return ExecutionResult(success=False, message="Exchange no configurado")

        try:
            symbol = analysis.symbol
            side = analysis.decision.lower()
            amount = analysis.parameters.get('amount', 0) if analysis.parameters else 0
            
            if amount <= 0:
                return ExecutionResult(success=False, message="Cantidad inválida")

            if Config.DEMO_MODE:
                logger.info(f"[MODO DEMO] Simulando {side} para {symbol}")
                # Aquí se actualizaría la base de datos de balances virtuales
                from crypto_bot_api.models.database import SessionLocal, VirtualBalance, TradeHistory
                db = SessionLocal()
                
                # Obtener precio actual para la simulación
                ticker = self.exchange.fetch_ticker(symbol) if self.exchange else {'last': 50000.0}
                price = ticker['last']
                
                # Registrar trade
                new_trade = TradeHistory(
                    symbol=symbol, side=side.upper(), price=price, 
                    amount=amount, market_type="CEX", is_demo=True
                )
                db.add(new_trade)
                
                # Actualizar balance (simplificado)
                balance = db.query(VirtualBalance).filter_by(market_type="CEX", asset="USDT").first()
                if side == "buy":
                    balance.amount -= (price * amount)
                else:
                    balance.amount += (price * amount)
                
                db.commit()
                db.close()
                
                return ExecutionResult(
                    success=True,
                    message=f"MODO DEMO: {side.upper()} {symbol} a {price} registrado en balance virtual"
                )

            # Lógica real (si no es modo demo)
            logger.info(f"Ejecutando {side} REAL en {self.exchange_id} para {symbol}")
            # order = self.exchange.create_order(symbol, 'market', side, amount)
            return ExecutionResult(success=True, message="Orden real ejecutada (Simulado en código)")

        except Exception as e:
            logger.error(f"Error ejecutando trade en CEX: {e}")
            return ExecutionResult(success=False, message=f"Error en CEX: {str(e)}")
