from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
from bson import ObjectId

from api.src.domain.entities.signal import Signal, SignalStatus, SignalAnalysis, Decision, Direction, RawSignal
from api.src.domain.ports.output.signal_repository import ISignalRepository
from api.src.domain.ports.output.ai_port import IAIPort
from api.src.domain.ports.output.notification_port import INotificationPort
from api.src.domain.ports.output.telegram_repository_port import ITelegramSignalRepository, ITelegramTradeRepository
from api.src.adapters.driven.persistence.mongodb import db as mongo_db

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
                    now = datetime.utcnow()
                    telegram_signal_doc = {
                        "signalId": current_id,
                        # store ObjectId for consistency; also keep openId for debugging
                        "userId": (config or {}).get("userId") or user_id,
                        "openId": user_id,
                        "source": source,
                        "chatId": chat_id,
                        "status": str(status),
                        "analysis": update_data,
                        # For UI/debugging: explicit creation time
                        "createdAt": now,
                        # Kept for backward compatibility with existing docs
                        "timestamp": now,
                    }
                    await self.telegram_signal_repository.save_signal(telegram_signal_doc)

                    if analysis.decision == Decision.REJECTED or analysis.direction == Direction.HOLD:
                        continue

                    # 4. PASO CRÍTICO: Crear el Bot (1:1 con la señal) + Trade workflow
                    if analysis.is_safe:
                        # Limit active telegram bots (0 = unlimited)
                        try:
                            max_tg = int(((config or {}).get("botStrategy") or {}).get("maxActiveTelegramBots") or 0)
                        except Exception:
                            max_tg = 0

                        if max_tg and max_tg > 0:
                            try:
                                # Prefer ObjectId user_oid if available
                                q_user = (config or {}).get("userId")
                                if user_oid is not None:
                                    q_user = user_oid

                                active_count = await mongo_db["telegram_bots"].count_documents({
                                    "userId": q_user,
                                    "status": {"$in": ["waiting_entry", "active"]},
                                })
                                if active_count >= max_tg:
                                    await self.signal_repository.update(current_id, {
                                        "status": SignalStatus.REJECTED,
                                        "executionMessage": f"Max active telegram bots reached ({max_tg}).",
                                    })
                                    continue
                            except Exception as e:
                                logger.warning(f"Failed checking maxActiveTelegramBots: {e}")

                        # Validate symbol exists on chosen exchange/market before creating bot
                        try:
                            from api.src.adapters.driven.exchange.market_validation import is_symbol_supported

                            chosen_exchange = None
                            try:
                                chosen_exchange = (analysis.parameters.exchangeId or "").strip().lower()
                            except Exception:
                                chosen_exchange = None

                            if not chosen_exchange:
                                chosen_exchange = ((config or {}).get("exchanges") or [{}])[0].get("exchangeId", "binance")

                            chosen_market = None
                            try:
                                chosen_market = analysis.market_type.value
                            except Exception:
                                chosen_market = None

                            ok = await is_symbol_supported(chosen_exchange, analysis.symbol, market_type=chosen_market)
                            if not ok:
                                await self.signal_repository.update(current_id, {
                                    "status": SignalStatus.REJECTED,
                                    "executionMessage": f"Symbol {analysis.symbol} not supported on {chosen_exchange} ({chosen_market})"
                                })
                                continue
                        except Exception as e:
                            logger.warning(f"Symbol validation skipped due to error: {e}")

                        # Create/Upsert telegram_bots (ObjectId) 1:1 with signalId
                        try:
                            bot_oid = ObjectId(current_id) if isinstance(current_id, str) and len(current_id) == 24 else ObjectId()

                            cfg_user_id = (config or {}).get("userId")
                            user_oid = None
                            if isinstance(cfg_user_id, ObjectId):
                                user_oid = cfg_user_id
                            elif isinstance(cfg_user_id, str) and len(cfg_user_id) == 24:
                                try:
                                    user_oid = ObjectId(cfg_user_id)
                                except Exception:
                                    user_oid = None

                            # Fallback: lookup user by openId so telegram_bots always stores ObjectId
                            if user_oid is None:
                                try:
                                    u = await mongo_db["users"].find_one({"openId": user_id})
                                    if u and isinstance(u.get("_id"), ObjectId):
                                        user_oid = u["_id"]
                                except Exception:
                                    user_oid = None

                            bot_doc = {
                                "_id": bot_oid,
                                "signalId": bot_oid,
                                "source": source,
                                "chatId": chat_id,
                                "symbol": analysis.symbol,
                                "side": analysis.direction.value,
                                "marketType": analysis.market_type.value,
                                "mode": "simulated" if (config or {}).get("demoMode", True) else "real",
                                "exchangeId": (analysis.parameters.exchangeId or ((config or {}).get("exchanges") or [{}])[0].get("exchangeId", "binance")),
                                "status": "waiting_entry",
                                "config": {
                                    "entryPrice": analysis.parameters.entry_price,
                                    "stopLoss": analysis.parameters.sl,
                                    "takeProfits": [
                                        {
                                            "price": tp.price,
                                            "percent": tp.percent,
                                            "qty": getattr(tp, "qty", None),
                                            "status": getattr(tp, "status", "pending"),
                                        }
                                        for tp in (analysis.parameters.tp or [])
                                    ],
                                    "leverage": analysis.parameters.leverage,
                                    "investment": analysis.parameters.investment or analysis.parameters.amount,
                                },
                                "createdAt": datetime.utcnow(),
                            }

                            # Expiration countdown (only if IA provided a time window)
                            try:
                                vfm = getattr(analysis.parameters, "validForMinutes", None)
                                if vfm is not None:
                                    mins = int(vfm)
                                    if mins > 0:
                                        bot_doc["expiresAt"] = datetime.utcnow() + timedelta(minutes=mins)
                            except Exception:
                                pass

                            # Upsert
                            # NOTE: do not include the same field in $setOnInsert and $set (Mongo conflict)
                            await mongo_db["telegram_bots"].update_one(
                                {"_id": bot_oid},
                                {
                                    "$setOnInsert": bot_doc,
                                    "$set": {"updatedAt": datetime.utcnow(), "userId": user_oid},
                                },
                                upsert=True,
                            )
                        except Exception as e:
                            logger.error(f"Failed creating telegram_bots doc for signal {current_id}: {e}")

                        # Crear items TP/SL en telegram_trades (1 doc por TP y 1 doc por SL) usando botId
                        try:
                            entry_val = analysis.parameters.entry_price
                            sl_val = analysis.parameters.sl
                            direction_val = analysis.direction.value if getattr(analysis, "direction", None) else None

                            # Build TP items with numeric targetPrice only
                            tp_items = []
                            for tp in (analysis.parameters.tp or []):
                                try:
                                    if tp is None:
                                        continue
                                    price = getattr(tp, "price", None)
                                    percent = getattr(tp, "percent", None)
                                    if price is None or percent is None:
                                        continue
                                    price_f = float(price)
                                    percent_f = float(percent)
                                    if price_f <= 0 or percent_f <= 0:
                                        continue

                                    # Direction sanity: LONG => TP above entry; SHORT => TP below entry
                                    if entry_val is not None and direction_val in ["LONG", "SHORT"]:
                                        try:
                                            entry_f = float(entry_val)
                                            if direction_val == "LONG" and price_f <= entry_f:
                                                continue
                                            if direction_val == "SHORT" and price_f >= entry_f:
                                                continue
                                        except Exception:
                                            pass

                                    tp_items.append({
                                        "targetPrice": price_f,
                                        "percent": percent_f,
                                    })
                                except Exception:
                                    continue

                            # Order by closeness to entry (if available)
                            if entry_val is not None:
                                try:
                                    entry_f = float(entry_val)
                                    tp_items.sort(key=lambda x: abs(x["targetPrice"] - entry_f))
                                except Exception:
                                    pass

                            # Reset any existing items for this bot (safe at creation time)
                            await mongo_db["telegram_trades"].delete_many({"userId": user_oid, "botId": bot_oid})

                            docs = []
                            now = datetime.utcnow()

                            # Entry item
                            if entry_val is not None:
                                try:
                                    docs.append({
                                        "userId": user_oid,
                                        "botId": bot_oid,
                                        "kind": "entry",
                                        "level": 0,
                                        "targetPrice": float(entry_val),
                                        "status": "active",
                                        "createdAt": now,
                                        "updatedAt": now,
                                    })
                                except Exception:
                                    pass

                            # SL item
                            if sl_val is not None:
                                try:
                                    docs.append({
                                        "userId": user_oid,
                                        "botId": bot_oid,
                                        "kind": "sl",
                                        "level": 0,
                                        "targetPrice": float(sl_val),
                                        "status": "active",
                                        "createdAt": now,
                                        "updatedAt": now,
                                    })
                                except Exception:
                                    pass

                            # TP items
                            for idx, tp in enumerate(tp_items, start=1):
                                docs.append({
                                    "userId": user_oid,
                                    "botId": bot_oid,
                                    "kind": "tp",
                                    "level": idx,
                                    "targetPrice": tp["targetPrice"],
                                    "percent": tp["percent"],
                                    "status": "pending",
                                    "createdAt": now,
                                    "updatedAt": now,
                                })

                            if docs:
                                await mongo_db["telegram_trades"].insert_many(docs)
                        except Exception as e:
                            logger.error(f"Failed creating telegram_trades items for bot {current_id}: {e}")

                        # Usar el servicio de trades inyectado (workflow legacy)
                        # Ensure legacy trade uses the bot's exchange/market (not global config.exchanges[0])
                        cfg2 = dict(config or {})
                        try:
                            cfg2["telegramExchangeId"] = bot_doc.get("exchangeId")
                            cfg2["telegramMarketType"] = bot_doc.get("marketType")
                        except Exception:
                            pass
                        result = await self.trade_service.create_telegram_trade(analysis, user_id, cfg2, signal_id=current_id)
                        
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
