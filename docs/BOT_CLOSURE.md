# Cierre de Bot - Liberar Wallet

**Fecha:** 2026-02-20  
**Estado:** ✅ Implementado  
**Issue:** Balance global se quedaba "trabado" en bots cerrados

---

## Problema

Cuando un bot simulado se cerraba (o eliminaba), la wallet asignada (`walletAllocated`) no se liberaba al balance virtual global. Esto causaba que:

- El balance disponible del usuario disminuía sin razón aparente
- No se podía reutilizar ese capital en nuevos bots
- El PnL realizado se perdía

---

## Solución

Endpoint `POST /api/bots/{bot_id}/close` que:

1. **Cierra posición abierta** (si existe)
   - Calcula PnL con precio de mercado
   - Actualiza posición a `CLOSED`
   - Abona capital + PnL al wallet del bot

2. **Libera wallet al balance global**
   - `walletAvailable` → balance virtual global
   - `walletRealizedPnl` → balance virtual global
   - Resetea wallet del bot a 0

3. **Actualiza estado del bot**
   - `status` → `closed`
   - `closedAt` → timestamp de cierre
   - `position` → `{qty: 0, avg_price: 0}`

4. **Emite evento WebSocket**
   - Topic: `user:{user_id}`
   - Evento: `bot_closed`
   - Payload: `{id, walletReleased, pnlRealized, status}`

---

## Endpoint

### `POST /api/bots/{bot_id}/close`

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response (200 OK):**
```json
{
  "status": "success",
  "bot_id": "64f5a1b2c3d4e5f6g7h8i9j0",
  "walletReleased": 150.50,
  "pnlRealized": 25.30,
  "finalStatus": "closed"
}
```

**Response (400 Bad Request):**
```json
{
  "detail": "Bot is already closed"
}
```

**Response (404 Not Found):**
```json
{
  "detail": "Bot not found or not authorized"
}
```

---

## Flujo Interno

```
┌─────────────────────────────────────────────────────────────┐
│  POST /api/bots/{bot_id}/close                              │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Verificar ownership (userId match)                      │
│     └─► Si falla → 404 Not Authorized                       │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Verificar estado actual                                 │
│     └─► Si status == "closed" → 400 Already Closed         │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Buscar posición OPEN en colección 'positions'           │
│     └─► Si existe → ejecutar _close_position()              │
│         • Calcular PnL con precio de mercado                │
│         • Actualizar posición a CLOSED                      │
│         • Abonar capital + PnL al wallet del bot            │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Liberar wallet (si mode == simulated)                   │
│     └─► ejecutar _release_wallet()                          │
│         • walletAvailable → virtual_balances (global)       │
│         • walletRealizedPnl → virtual_balances (global)     │
│         • Resetear wallet del bot a 0                       │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Actualizar bot a 'closed'                               │
│     └─► $set: {status, closedAt, side, position}            │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Emitir evento WebSocket                                 │
│     └─► bot_closed → user:{user_id}                         │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  Response: {success, walletReleased, pnlRealized, status}   │
└─────────────────────────────────────────────────────────────┘
```

---

## Ejemplos de Uso

### cURL
```bash
curl -X POST http://localhost:8000/api/bots/64f5a1b2c3d4e5f6g7h8i9j0/close \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

### Python (httpx)
```python
import httpx

async def close_bot(bot_id: str, token: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:8000/api/bots/{bot_id}/close",
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.json()

# Uso
result = await close_bot("64f5a1b2c3d4e5f6g7h8i9j0", "eyJhbGc...")
print(f"Wallet liberada: ${result['walletReleased']}")
print(f"PnL realizado: ${result['pnlRealized']}")
```

### JavaScript (fetch)
```javascript
async function closeBot(botId, token) {
  const response = await fetch(`http://localhost:8000/api/bots/${botId}/close`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  const result = await response.json();
  console.log(`Wallet liberada: $${result.walletReleased}`);
  console.log(`PnL realizado: $${result.pnlRealized}`);
  
  return result;
}
```

---

## Testing

### Tests Automatizados
```bash
cd api
python -m pytest tests/test_bot_close_wallet.py -v
```

**Tests incluidos:**
1. `test_close_bot_without_position` → Cierra bot sin posición, libera wallet
2. `test_close_bot_with_position` → Cierra bot con posición, calcula PnL + libera wallet
3. `test_close_already_closed_bot` → Intenta cerrar bot ya cerrado (error esperado)
4. `test_close_bot_unauthorized` → Intenta cerrar bot de otro usuario (error esperado)

### Testing Manual
```bash
cd api
python scripts/test_bot_close.py --bot-id <BOT_ID> --email <EMAIL> --password <PASSWORD>
```

---

## Invariants (Garantías)

✅ **Ownership:** Solo el dueño del bot puede cerrarlo  
✅ **Idempotencia:** No se puede cerrar bot ya cerrado  
✅ **Atomicidad:** Si falla un paso, se hace rollback (transacción MongoDB)  
✅ **Consistencia:** Wallet del bot = 0 después de cerrar  
✅ **Trazabilidad:** Evento WS `bot_closed` emitido para actualizar frontend  

---

## Archivos Modificados

| Archivo | Cambios |
|---------|---------|
| `api/src/application/services/bot_service.py` | +3 métodos: `close_bot()`, `_close_position()`, `_release_wallet()` |
| `api/src/adapters/driving/api/routers/bot_router.py` | +1 endpoint: `POST /{bot_id}/close` |
| `docs/FLOW_LOCKS.md` | +1 sección: BOT CLOSURE (zona bloqueada) |
| `tests/test_bot_close_wallet.py` | +4 tests automatizados |
| `scripts/test_bot_close.py` | +1 script de testing manual |

---

## Próximos Pasos

1. ✅ Implementación completada
2. ⏳ Tests automatizados (pendiente ejecutar)
3. ⏳ Testing manual en entorno de desarrollo
4. ⏳ Integración con frontend (botón "Close Bot" en dashboard)
5. ⏳ Documentación de API (OpenAPI/Swagger)

---

## Notas Importantes

### Modo Simulado vs Real
- **Simulado:** Libera wallet a `virtual_balances` (MongoDB)
- **Real:** Esta funcionalidad NO aplica (no hay sub-wallet en modo real)

### PnL Negativo
- Si el bot tiene PnL negativo al cerrar, el capital retornado será menor al original
- Ejemplo: `$100 asignados - $20 PnL negativo = $80 liberados`

### Posiciones Múltiples
- Actualmente un bot tiene UNA posición abierta máxima
- Si hay múltiples (bug), se cierra la primera encontrada

---

**Implementado por:** Trinity ⚡  
**Revisión pendiente:** Juan
