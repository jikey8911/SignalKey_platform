# FLOW_LOCKS.md

Este documento marca zonas del código que se consideran **estables** ("bloqueadas") porque ya funcionan.

> Bloqueadas = no tocar sin revisión + pruebas mínimas.
> No es un lock real de Git; es una convención para evitar regresiones.

## TRAINING (modelos globales)

**Archivos bloqueados:**
- `api/src/application/services/ml_service.py`
- `api/src/adapters/driving/api/routers/ml_router.py`
- `api/src/domain/services/strategy_trainer.py`

**Pruebas mínimas antes de merge:**
- Entrenar 3 símbolos (BTC/USDT, XRP/USDT, ACE/USDT) en spot
- Verificar que genera .pkl en `api/data/models/spot/`
- Verificar que `predict` funciona para 1 estrategia

## BACKTEST (WS + Service)

**Archivos bloqueados:**
- `api/src/application/services/backtest_service.py`
- `api/src/adapters/driving/api/routers/websocket_router.py` (handlers `run_*_backtest_ws`)

**Pruebas mínimas:**
- `run_single_backtest_ws`
- `run_batch_backtest_ws`
- Validar que no spamea logs (INFO solo winner)

## BOT CREATION (Deploy + Guardrails)

**Archivos bloqueados:**
- `api/src/adapters/driving/api/routers/backtest_router.py` (endpoint `deploy_bot`)
- `api/src/adapters/driving/api/routers/bot_router.py` (endpoint `create_new_bot`)
- `api/src/adapters/driven/persistence/mongodb_bot_repository.py` (guardrail final `save()`)
- `api/src/application/services/execution_engine.py` (guardrail `process_signal()`)
- `api/src/application/services/bot_feature_state_service.py` (initialize_for_bot)

**Invariants:**
- `bot.amount > 0` siempre (rechazado en repositorio si <= 0)
- `bot.exchange_id` siempre seteado (okx fallback)
- `bot.market_type` siempre seteado (spot/futures)
- `bot_feature_states` se crea automáticamente al crear bot

**Pruebas mínimas:**
- `python tests/test_bot_creation_guardrails.py` (3/3 pass)
- Crear bot desde Backtest → Deploy → validar amount > 0 en BD
- Crear bot desde Bots → Create → validar amount > 0 en BD
- Verificar `bot_feature_states` existe con windowCaldas > 0

## BOT CLOSURE (Close + Wallet Release)

**Archivos bloqueados:**
- `api/src/adapters/driving/api/routers/bot_router.py` (endpoint `POST /{bot_id}/close`)
- `api/src/application/services/bot_service.py` (métodos `close_bot`, `_close_position`, `_release_wallet`)

**Invariants:**
- Al cerrar bot: posición abierta se cierra con PnL calculado
- Al cerrar bot: walletAllocated se libera al balance global
- Al cerrar bot: estado cambia a `closed` + `closedAt` timestamp
- Solo el dueño del bot puede cerrarlo (verificación de ownership)
- No se puede cerrar bot ya cerrado (idempotencia)

**Flujo:**
1. Verificar ownership del bot
2. Si hay posición OPEN → cerrar con precio de mercado (calcula PnL)
3. Liberar `walletAvailable` + `walletRealizedPnl` al balance virtual global
4. Resetear wallet del bot a 0
5. Actualizar estado a `closed`
6. Emitir evento WS `bot_closed`

**Pruebas mínimas:**
- `python tests/test_bot_close_wallet.py` (4/4 pass)
- Cerrar bot sin posición → valida liberación de wallet
- Cerrar bot con posición → valida cierre + PnL + liberación
- Cerrar bot ya cerrado → retorna error o estado cerrado
- Cerrar bot de otro usuario → retorna "Not authorized"

## Nota
Si se necesita cambiar una zona bloqueada, debe:
1) abrir issue/nota de motivo
2) hacer cambios en branch dedicada
3) correr pruebas mínimas
