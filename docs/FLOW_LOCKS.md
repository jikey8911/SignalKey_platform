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

## Nota
Si se necesita cambiar una zona bloqueada, debe:
1) abrir issue/nota de motivo
2) hacer cambios en branch dedicada
3) correr pruebas mínimas
