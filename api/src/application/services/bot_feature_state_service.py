from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
import os

import pandas as pd

from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
from api.src.adapters.driven.persistence.mongodb_bot_feature_state_repository import (
    MongoBotFeatureStateRepository,
)
from api.src.adapters.driven.persistence.mongodb_bot_feature_history_repository import (
    MongoBotFeatureHistoryRepository,
)
from api.src.adapters.driven.persistence.mongodb import db
from api.src.domain.services.strategy_trainer import StrategyTrainer


class BotFeatureStateService:
    """Inicializa/persiste features de estrategia por bot al crearse.

    Nota: esta versión crea snapshot inicial. La actualización incremental por cierre de vela
    se implementa en una fase siguiente.
    """

    def __init__(self, repository: MongoBotFeatureStateRepository | None = None):
        self.repo = repository or MongoBotFeatureStateRepository()
        self.history_repo = MongoBotFeatureHistoryRepository()
        self.trainer = StrategyTrainer()

    async def initialize_for_bot(
        self,
        *,
        bot_id: str,
        user_id: Any,
        user_open_id: str,
        symbol: str,
        timeframe: str,
        market_type: str,
        exchange_id: str,
        strategy_name: str,
        candles_limit: int = 200,
    ) -> Dict[str, Any]:
        await self.repo.ensure_indexes()
        await self.history_repo.ensure_indexes()

        market_norm = (market_type or "spot").lower()
        if market_norm == "cex":
            market_norm = "spot"

        StrategyClass = self.trainer.load_strategy_class(strategy_name, market_norm)
        if not StrategyClass:
            return {"ok": False, "reason": "strategy_class_not_found"}

        # Inyectar memoria operativa mínima (bootstrap): no hay last_action real aún.
        cfg = {"operational_context": {"last_action_side": None, "last_action_price": 0.0, "last_action_ts": None}}
        strategy = StrategyClass(cfg)
        base_features: List[str] = strategy.get_features() or []

        # Histórico inicial (CCXT only)
        # IMPORTANT: historical candles for feature bootstrap must be fetched via PUBLIC CCXT path
        # (no private account credentials), to avoid exchange private-endpoint failures.
        df = await ccxt_service.get_historical_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=candles_limit,
            user_id=None,
            exchange_id=exchange_id,
            market_type=market_norm,
        )

        # Optional CCXT-only fallback exchange for bootstrap (when the bot's exchange is unreachable)
        if df is None or df.empty:
            fb_exchange = (os.getenv("FEATURE_BOOTSTRAP_FALLBACK_EXCHANGE") or "").strip().lower()
            if fb_exchange and fb_exchange != str(exchange_id).lower():
                df = await ccxt_service.get_historical_data(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=candles_limit,
                    user_id=None,
                    exchange_id=fb_exchange,
                    market_type=market_norm,
                )

        if df is None or df.empty:
            # Crear documento mínimo para que el bot tenga estado aunque falle el bootstrap.
            payload = {
                "botId": bot_id,
                "userId": user_id,
                "userOpenId": user_open_id,
                "strategyName": strategy_name,
                "symbol": symbol,
                "exchangeId": exchange_id,
                "timeframe": timeframe,
                "marketType": market_norm,
                "features": [],
                "latestFeatures": {},
                "windowCandles": [],
                "lastCandleTimestamp": None,
                "featureRows": 0,
                "initializedAt": datetime.utcnow(),
            }
            doc_id = await self.repo.upsert_state(payload)
            return {"ok": False, "reason": "empty_history", "docId": doc_id}

        processed = strategy.apply(df.copy(), current_position={"qty": 0, "avg_price": 0})
        if processed is None or processed.empty:
            payload = {
                "botId": bot_id,
                "userId": user_id,
                "userOpenId": user_open_id,
                "strategyName": strategy_name,
                "symbol": symbol,
                "exchangeId": exchange_id,
                "timeframe": timeframe,
                "marketType": market_norm,
                "features": [],
                "latestFeatures": {},
                "windowCandles": [],
                "lastCandleTimestamp": None,
                "featureRows": 0,
                "initializedAt": datetime.utcnow(),
            }
            doc_id = await self.repo.upsert_state(payload)
            return {"ok": False, "reason": "empty_processed", "docId": doc_id}

        # Features usadas por modelo (match con MLService)
        processed = processed.copy()
        processed["in_position"] = 0
        processed["current_pnl"] = 0.0

        model_features = list(base_features) + ["in_position", "current_pnl"]
        missing = [c for c in model_features if c not in processed.columns]
        if missing:
            return {"ok": False, "reason": f"missing_features:{','.join(missing)}"}

        valid = processed[model_features].dropna()
        if valid.empty:
            return {"ok": False, "reason": "no_valid_feature_rows"}

        latest_idx = valid.index[-1]
        latest_features = {
            k: (float(valid.loc[latest_idx, k]) if pd.notna(valid.loc[latest_idx, k]) else None)
            for k in model_features
        }

        # Build candles + features per candle (window + history)
        merged = processed.copy()
        merged = merged.dropna(subset=model_features)
        merged = merged.tail(120)

        candles_payload = []
        history_docs = []
        for idx, row in merged.iterrows():
            ts_iso = idx.to_pydatetime().isoformat() if isinstance(idx, pd.Timestamp) else str(idx)
            feat_row = {
                k: (float(row.get(k)) if pd.notna(row.get(k)) else None)
                for k in model_features
            }
            candle_obj = {
                "timestamp": ts_iso,
                "open": float(row.get("open", 0) or 0),
                "high": float(row.get("high", 0) or 0),
                "low": float(row.get("low", 0) or 0),
                "close": float(row.get("close", 0) or 0),
                "volume": float(row.get("volume", 0) or 0),
                "features": feat_row,
            }
            candles_payload.append(candle_obj)
            history_docs.append(
                {
                    "botId": bot_id,
                    "userId": user_id,
                    "strategyName": strategy_name,
                    "symbol": symbol,
                    "exchangeId": exchange_id,
                    "timeframe": timeframe,
                    "marketType": market_norm,
                    "candleTs": ts_iso,
                    "candle": {
                        "open": candle_obj["open"],
                        "high": candle_obj["high"],
                        "low": candle_obj["low"],
                        "close": candle_obj["close"],
                        "volume": candle_obj["volume"],
                    },
                    "features": feat_row,
                }
            )

        payload = {
            "botId": bot_id,
            "userId": user_id,
            "userOpenId": user_open_id,
            "strategyName": strategy_name,
            "symbol": symbol,
            "exchangeId": exchange_id,
            "timeframe": timeframe,
            "marketType": market_norm,
            "features": model_features,
            "latestFeatures": latest_features,
            "windowCandles": candles_payload,
            "lastCandleTimestamp": candles_payload[-1]["timestamp"] if candles_payload else None,
            "featureRows": int(len(valid)),
            "initializedAt": datetime.utcnow(),
        }

        doc_id = await self.repo.upsert_state(payload)
        written = await self.history_repo.upsert_many(history_docs)
        return {
            "ok": True,
            "docId": doc_id,
            "featureCount": len(model_features),
            "rows": int(len(valid)),
            "historyUpserts": int(written),
        }

    async def update_on_candle_close(self, *, bot: Dict[str, Any], candles_df: pd.DataFrame) -> Dict[str, Any]:
        """Update bot_feature_states/history using provided closed-candle dataframe.

        candles_df should contain historical candles up to the *last closed* candle.
        """
        try:
            if candles_df is None or candles_df.empty:
                return {"ok": False, "reason": "empty_candles_df"}

            bot_id = str(bot.get("_id") or bot.get("id") or "")
            user_id = bot.get("user_id") or bot.get("userId")
            if not bot_id or user_id is None:
                return {"ok": False, "reason": "missing_bot_or_user"}

            user_doc = await db.users.find_one({"_id": user_id})
            user_open_id = user_doc.get("openId") if user_doc else None

            strategy_name = bot.get("strategy_name") or "auto"
            market_norm = str(bot.get("market_type") or bot.get("marketType") or "spot").lower()
            if market_norm == "cex":
                market_norm = "spot"

            StrategyClass = self.trainer.load_strategy_class(strategy_name, market_norm)
            if not StrategyClass:
                return {"ok": False, "reason": "strategy_class_not_found"}

            cfg = (bot.get("config") or {}).copy()
            # Inyectar memoria operativa para features (no consulta DB)
            cfg["operational_context"] = {
                "last_action_side": bot.get("side"),
                "last_action_price": float((bot.get("position") or {}).get("avg_price", 0) or 0),
                "last_action_ts": bot.get("last_execution") or bot.get("last_execution_at") or bot.get("updated_at"),
            }
            strategy = StrategyClass(cfg)
            base_features: List[str] = strategy.get_features() or []

            processed = strategy.apply(candles_df.copy(), current_position=bot.get("position") or {"qty": 0, "avg_price": 0})
            if processed is None or processed.empty:
                return {"ok": False, "reason": "empty_processed"}

            processed = processed.copy()
            if "in_position" not in processed.columns:
                in_pos = 1 if float((bot.get("position") or {}).get("qty", 0) or 0) > 0 else 0
                processed["in_position"] = in_pos
            if "current_pnl" not in processed.columns:
                processed["current_pnl"] = 0.0

            model_features = list(base_features) + ["in_position", "current_pnl"]
            missing = [c for c in model_features if c not in processed.columns]
            if missing:
                return {"ok": False, "reason": f"missing_features:{','.join(missing)}"}

            valid = processed[model_features].dropna()
            if valid.empty:
                return {"ok": False, "reason": "no_valid_feature_rows"}

            latest_idx = valid.index[-1]
            latest_features = {
                k: (float(valid.loc[latest_idx, k]) if pd.notna(valid.loc[latest_idx, k]) else None)
                for k in model_features
            }

            merged = processed.dropna(subset=model_features).tail(120)
            candles_payload = []
            for idx, row in merged.iterrows():
                ts_iso = idx.to_pydatetime().isoformat() if isinstance(idx, pd.Timestamp) else str(idx)
                feat_row = {k: (float(row.get(k)) if pd.notna(row.get(k)) else None) for k in model_features}
                candles_payload.append({
                    "timestamp": ts_iso,
                    "open": float(row.get("open", 0) or 0),
                    "high": float(row.get("high", 0) or 0),
                    "low": float(row.get("low", 0) or 0),
                    "close": float(row.get("close", 0) or 0),
                    "volume": float(row.get("volume", 0) or 0),
                    "features": feat_row,
                })

            payload = {
                "botId": bot_id,
                "userId": user_id,
                "userOpenId": user_open_id,
                "strategyName": strategy_name,
                "symbol": bot.get("symbol"),
                "exchangeId": (bot.get("exchange_id") or bot.get("exchangeId") or "okx"),
                "timeframe": bot.get("timeframe") or "15m",
                "marketType": market_norm,
                "features": model_features,
                "latestFeatures": latest_features,
                "windowCandles": candles_payload,
                "lastCandleTimestamp": candles_payload[-1]["timestamp"] if candles_payload else None,
                "featureRows": int(len(valid)),
            }

            doc_id = await self.repo.upsert_state(payload)

            # Nota (Juan): en runtime normal NO escribimos bot_feature_history aquí.
            # Solo mantenemos el estado vivo en bot_feature_states.windowCandles/latestFeatures.
            # El histórico se puede poblar por backfill o por una fase posterior.

            return {"ok": True, "docId": doc_id, "rows": int(len(valid))}
        except Exception as e:
            return {"ok": False, "reason": f"update_on_candle_close_error:{e}"}
