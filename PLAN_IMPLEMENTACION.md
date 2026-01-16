# 🚀 Plan de Implementación - SignalKey Platform

**Fecha de Creación**: 16 de Enero de 2026  
**Objetivo General**: Integrar la API Python (FastAPI) con la aplicación Web (React/tRPC) para crear un sistema unificado de trading automatizado.

---

## 📋 Resumen Ejecutivo

Este plan de implementación está diseñado para integrar gradualmente los dos sistemas independientes (API Python y Web App) en una plataforma cohesiva y funcional. El plan se divide en **4 sprints** que abordan desde la unificación de datos hasta la ejecución real de trades.

### Duración Total Estimada
- **Sprint 1**: 2 semanas
- **Sprint 2**: 2 semanas  
- **Sprint 3**: 3 semanas
- **Sprint 4**: 3 semanas
- **Total**: 10 semanas (~2.5 meses)

### Equipo Recomendado
- 1 Backend Developer (Python/FastAPI)
- 1 Full-stack Developer (TypeScript/Node.js/React)
- 1 DevOps Engineer (part-time)
- 1 QA Engineer (part-time)

---

## 🟩 Sprint 1: Unificación de la Capa de Datos (Cimientos)

**Duración**: 2 semanas  
**Objetivo**: Eliminar la duplicación de bases de datos y centralizar la verdad en MySQL.

### 📌 Tareas Principales

#### 1.1 Migración de Esquema (3 días)

**Responsable**: Backend Developer  
**Prioridad**: 🔴 Crítica

**Actividades**:
- [ ] Analizar esquemas actuales de SQLite y MySQL
- [ ] Diseñar esquema unificado en MySQL
- [ ] Crear script de migración de datos existentes
- [ ] Validar integridad de datos migrados

**Entregables**:
```sql
-- Script: migrations/001_unify_databases.sql
-- Migra VirtualBalance y TradeHistory de SQLite a MySQL
```

**Archivos a Crear**:
- `migrations/001_unify_databases.sql`
- `migrations/migrate_sqlite_to_mysql.py`

**Criterios de Aceptación**:
- ✅ Todos los datos de SQLite están en MySQL
- ✅ No hay pérdida de datos
- ✅ Esquemas son compatibles con ambos sistemas

---

#### 1.2 Refactor de Persistencia en Python (4 días)

**Responsable**: Backend Developer  
**Prioridad**: 🔴 Crítica

**Actividades**:
- [ ] Instalar SQLAlchemy en la API Python
- [ ] Crear modelos SQLAlchemy para MySQL
- [ ] Refactorizar `CEXService` para usar MySQL
- [ ] Refactorizar `DEXService` para usar MySQL
- [ ] Actualizar `BacktestService` si es necesario
- [ ] Eliminar dependencias de SQLite

**Entregables**:
```python
# api/models/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "mysql+pymysql://user:pass@host:3306/signalkey"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
```

**Archivos a Modificar**:
- `api/models/database.py` (refactor completo)
- `api/services/cex_service.py`
- `api/services/dex_service.py`
- `api/requirements.txt` (agregar `sqlalchemy`, `pymysql`)

**Criterios de Aceptación**:
- ✅ API Python se conecta exitosamente a MySQL
- ✅ Trades se guardan en MySQL
- ✅ No hay referencias a SQLite en el código

---

#### 1.3 Sincronización de Modelos (2 días)

**Responsable**: Full-stack Developer  
**Prioridad**: 🟡 Alta

**Actividades**:
- [ ] Comparar modelos de Drizzle (TypeScript) con SQLAlchemy (Python)
- [ ] Asegurar que los tipos de datos coincidan
- [ ] Actualizar migraciones de Drizzle si es necesario
- [ ] Documentar el esquema unificado

**Entregables**:
- Documento de mapeo de campos
- Esquema actualizado en `web/drizzle/schema.ts`

**Archivos a Modificar**:
- `web/drizzle/schema.ts` (si hay cambios)
- `api/models/schemas.py` (sincronizar con Drizzle)

**Criterios de Aceptación**:
- ✅ Los campos de `trades` en MySQL son compatibles con Python y TypeScript
- ✅ No hay conflictos de tipos de datos
- ✅ Documentación actualizada

---

#### 1.4 Configuración de Entorno (2 días)

**Responsable**: DevOps Engineer  
**Prioridad**: 🟡 Alta

**Actividades**:
- [ ] Crear `.env.shared` con credenciales de MySQL
- [ ] Actualizar `.env` de la API Python
- [ ] Actualizar `.env` de la Web App
- [ ] Configurar variables de entorno en desarrollo
- [ ] Documentar proceso de configuración

**Entregables**:
```bash
# .env.shared
DATABASE_HOST=localhost
DATABASE_PORT=3306
DATABASE_NAME=signalkey
DATABASE_USER=signalkey_user
DATABASE_PASSWORD=secure_password
```

**Archivos a Crear/Modificar**:
- `.env.shared` (nuevo)
- `api/.env.example` (actualizar)
- `web/.env.example` (actualizar)
- `README.md` (actualizar instrucciones)

**Criterios de Aceptación**:
- ✅ Ambos servicios usan las mismas credenciales de DB
- ✅ Configuración documentada
- ✅ Fácil de replicar en otros entornos

---

### 📊 Métricas de Éxito - Sprint 1

| Métrica | Objetivo | Medición |
|---------|----------|----------|
| Migración de datos | 100% | Todos los registros migrados |
| Conexión a MySQL | Exitosa | API Python conecta sin errores |
| Tests pasando | 100% | Todos los tests de integración pasan |
| Tiempo de respuesta | < 200ms | Queries a MySQL |

---

## 🟨 Sprint 2: Seguridad y Autenticación Inter-Servicios

**Duración**: 2 semanas  
**Objetivo**: Proteger los endpoints de la API y establecer una comunicación segura entre Node.js y Python.

### 📌 Tareas Principales

#### 2.1 Middleware de Auth en FastAPI (3 días)

**Responsable**: Backend Developer  
**Prioridad**: 🔴 Crítica

**Actividades**:
- [ ] Implementar middleware de autenticación JWT en FastAPI
- [ ] Crear endpoint de generación de tokens
- [ ] Proteger endpoints sensibles (`/webhook/signal`, `/backtest`)
- [ ] Implementar rate limiting
- [ ] Agregar logging de accesos

**Entregables**:
```python
# api/middleware/auth.py
from fastapi import Security, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    # Validar JWT
    if not is_valid_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")
    return token
```

**Archivos a Crear**:
- `api/middleware/auth.py`
- `api/utils/jwt_handler.py`

**Archivos a Modificar**:
- `api/main.py` (agregar middleware)
- `api/requirements.txt` (agregar `python-jose`, `passlib`)

**Criterios de Aceptación**:
- ✅ Endpoints protegidos requieren token válido
- ✅ Tokens expiran después de 24 horas
- ✅ Rate limiting funciona (max 100 req/min)
- ✅ Logs de acceso se guardan correctamente

---

#### 2.2 Encriptación de Credenciales (4 días)

**Responsable**: Full-stack Developer  
**Prioridad**: 🔴 Crítica

**Actividades**:
- [ ] Implementar servicio de encriptación AES-256 en Node.js
- [ ] Crear funciones de encrypt/decrypt
- [ ] Modificar `updateConfig` para encriptar antes de guardar
- [ ] Modificar `getConfig` para desencriptar al leer
- [ ] Actualizar esquema de DB si es necesario
- [ ] Implementar rotación de claves de encriptación

**Entregables**:
```typescript
// web/server/services/encryption.ts
import crypto from 'crypto';

const ALGORITHM = 'aes-256-gcm';
const KEY = process.env.ENCRYPTION_KEY!;

export function encrypt(text: string): string {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv(ALGORITHM, Buffer.from(KEY, 'hex'), iv);
  let encrypted = cipher.update(text, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  const authTag = cipher.getAuthTag();
  return iv.toString('hex') + ':' + authTag.toString('hex') + ':' + encrypted;
}

export function decrypt(encryptedData: string): string {
  const parts = encryptedData.split(':');
  const iv = Buffer.from(parts[0], 'hex');
  const authTag = Buffer.from(parts[1], 'hex');
  const encrypted = parts[2];
  const decipher = crypto.createDecipheriv(ALGORITHM, Buffer.from(KEY, 'hex'), iv);
  decipher.setAuthTag(authTag);
  let decrypted = decipher.update(encrypted, 'hex', 'utf8');
  decrypted += decipher.final('utf8');
  return decrypted;
}
```

**Archivos a Crear**:
- `web/server/services/encryption.ts`
- `web/server/services/credentialManager.ts`

**Archivos a Modificar**:
- `web/server/db.ts` (usar encryption en getAppConfig/upsertAppConfig)
- `web/server/routers.ts` (actualizar trading.updateConfig)

**Criterios de Aceptación**:
- ✅ API Keys se guardan encriptadas en MySQL
- ✅ Desencriptación funciona correctamente
- ✅ Clave de encriptación está en variable de entorno
- ✅ No hay credenciales en texto plano en la DB

---

#### 2.3 Servicio Proxy en Node (3 días)

**Responsable**: Full-stack Developer  
**Prioridad**: 🟡 Alta

**Actividades**:
- [ ] Crear servicio proxy para comunicación con FastAPI
- [ ] Implementar manejo de tokens JWT
- [ ] Agregar retry logic para requests fallidos
- [ ] Implementar timeout handling
- [ ] Agregar logging de requests

**Entregables**:
```typescript
// web/server/services/pythonApiProxy.ts
import fetch from 'node-fetch';

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000';
const API_TOKEN = process.env.PYTHON_API_TOKEN;

export async function callPythonApi<T>(
  endpoint: string, 
  data?: any, 
  method: 'GET' | 'POST' = 'POST'
): Promise<T> {
  const url = `${PYTHON_API_URL}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_TOKEN}`
      },
      body: data ? JSON.stringify(data) : undefined,
      timeout: 30000 // 30 segundos
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }

    return await response.json() as T;
  } catch (error) {
    console.error(`Error calling Python API ${endpoint}:`, error);
    throw error;
  }
}

// Funciones específicas
export async function runBacktest(symbol: string, days: number, timeframe: string) {
  return callPythonApi(`/backtest/${symbol}?days=${days}&timeframe=${timeframe}`, null, 'GET');
}

export async function sendSignal(signal: any) {
  return callPythonApi('/webhook/signal', signal);
}
```

**Archivos a Crear**:
- `web/server/services/pythonApiProxy.ts`

**Archivos a Modificar**:
- `web/server/routers.ts` (agregar procedures que usen el proxy)

**Criterios de Aceptación**:
- ✅ Proxy se comunica exitosamente con FastAPI
- ✅ Tokens JWT se incluyen en las peticiones
- ✅ Retry logic funciona (3 intentos)
- ✅ Timeouts se manejan correctamente

---

#### 2.4 Validación de Secrets (2 días)

**Responsable**: Full-stack Developer  
**Prioridad**: 🟢 Media

**Actividades**:
- [ ] Crear endpoint de validación de credenciales
- [ ] Implementar validación de API Keys de exchanges
- [ ] Agregar feedback visual en la UI
- [ ] Implementar validación de Gemini API Key
- [ ] Agregar tests de validación

**Entregables**:
```typescript
// Nuevo procedure en trading router
validateCredentials: protectedProcedure
  .input(z.object({
    exchangeId: z.string(),
    apiKey: z.string(),
    secret: z.string(),
    password: z.string().optional(),
    uid: z.string().optional()
  }))
  .mutation(async ({ input }) => {
    // Validar credenciales usando CCXT
    const ccxt = require('ccxt');
    const exchange = new ccxt[input.exchangeId]({
      apiKey: input.apiKey,
      secret: input.secret,
      password: input.password,
      uid: input.uid
    });
    
    try {
      await exchange.fetchBalance();
      return { valid: true, message: 'Credenciales válidas' };
    } catch (error) {
      return { valid: false, message: error.message };
    }
  })
```

**Archivos a Modificar**:
- `web/server/routers.ts` (agregar validateCredentials)
- `web/client/src/pages/Settings.tsx` (agregar botón de validación)

**Criterios de Aceptación**:
- ✅ Validación de credenciales funciona para Binance, OKX, Bybit
- ✅ UI muestra feedback claro (válido/inválido)
- ✅ No se guardan credenciales inválidas
- ✅ Validación de Gemini API Key funciona

---

### 📊 Métricas de Éxito - Sprint 2

| Métrica | Objetivo | Medición |
|---------|----------|----------|
| Endpoints protegidos | 100% | Todos requieren auth |
| Credenciales encriptadas | 100% | No hay texto plano en DB |
| Validación exitosa | > 95% | Credenciales válidas detectadas |
| Tiempo de validación | < 5s | Por exchange |

---

## 🟧 Sprint 3: Integración de Funcionalidades Críticas

**Duración**: 3 semanas  
**Objetivo**: Conectar la interfaz de usuario con la lógica real de trading y backtesting.

### 📌 Tareas Principales

#### 3.1 Conexión de Backtest (3 días)

**Responsable**: Full-stack Developer  
**Prioridad**: 🟡 Alta

**Actividades**:
- [ ] Crear procedure `runBacktest` en tRPC
- [ ] Modificar `Backtest.tsx` para usar el procedure
- [ ] Implementar manejo de loading states
- [ ] Agregar visualización de resultados reales
- [ ] Implementar caché de resultados
- [ ] Agregar gráfico de equity curve

**Entregables**:
```typescript
// En web/server/routers.ts
runBacktest: protectedProcedure
  .input(z.object({
    symbol: z.string(),
    days: z.number().min(1).max(365),
    timeframe: z.enum(['1m', '5m', '15m', '1h', '4h', '1d'])
  }))
  .mutation(async ({ input }) => {
    const { runBacktest } = await import('./services/pythonApiProxy');
    return await runBacktest(
      input.symbol.replace('-', '/'), 
      input.days, 
      input.timeframe
    );
  })
```

**Archivos a Modificar**:
- `web/server/routers.ts` (agregar runBacktest)
- `web/server/services/pythonApiProxy.ts` (agregar función runBacktest)
- `web/client/src/pages/Backtest.tsx` (usar tRPC en lugar de mock)

**Criterios de Aceptación**:
- ✅ Backtest se ejecuta con datos reales de la API
- ✅ Resultados se muestran correctamente en la UI
- ✅ Loading states funcionan
- ✅ Errores se manejan apropiadamente

---

#### 3.2 Refactor de Señales (5 días)

**Responsable**: Backend Developer  
**Prioridad**: 🔴 Crítica

**Actividades**:
- [ ] Modificar webhook para guardar en MySQL
- [ ] Actualizar `GeminiService` para incluir userId
- [ ] Crear sistema de asociación usuario-señal
- [ ] Implementar guardado de señales en `trading_signals`
- [ ] Actualizar guardado de trades con `signalId`
- [ ] Agregar endpoint para consultar señales por usuario

**Entregables**:
```python
# api/main.py - Actualizado
@app.post("/webhook/signal")
async def receive_signal(
    signal: TradingSignal, 
    background_tasks: BackgroundTasks,
    user_id: int = Header(...)  # Usuario desde token JWT
):
    background_tasks.add_task(process_signal_task, signal, user_id)
    return {"status": "Signal received and processing in background"}

async def process_signal_task(signal: TradingSignal, user_id: int):
    # 1. Analizar con Gemini
    analysis = await gemini_service.analyze_signal(signal.raw_text)
    
    # 2. Guardar señal en MySQL
    db = SessionLocal()
    new_signal = TradingSignalDB(
        user_id=user_id,
        source=signal.source,
        raw_text=signal.raw_text,
        decision=analysis.decision,
        symbol=analysis.symbol,
        market_type=analysis.market_type,
        confidence=analysis.confidence,
        reasoning=analysis.reasoning,
        status="pending"
    )
    db.add(new_signal)
    db.commit()
    signal_id = new_signal.id
    
    # 3. Ejecutar operación si no es HOLD
    if analysis.decision != "HOLD":
        if analysis.market_type == "DEX":
            result = await dex_service.execute_trade(analysis, user_id, signal_id)
        else:
            result = await cex_service.execute_trade(analysis, user_id, signal_id)
        
        # 4. Actualizar estado de la señal
        new_signal.status = "executed" if result.success else "failed"
        db.commit()
    
    db.close()
```

**Archivos a Modificar**:
- `api/main.py` (refactor completo de process_signal_task)
- `api/services/cex_service.py` (agregar user_id y signal_id)
- `api/services/dex_service.py` (agregar user_id y signal_id)
- `api/models/database.py` (agregar modelo TradingSignalDB)

**Criterios de Aceptación**:
- ✅ Señales se guardan en MySQL con userId
- ✅ Trades tienen referencia a signalId
- ✅ Estado de señales se actualiza correctamente
- ✅ Web App puede consultar señales del usuario

---

#### 3.3 Dashboard en Tiempo Real (6 días)

**Responsable**: Full-stack Developer  
**Prioridad**: 🔴 Crítica

**Actividades**:
- [ ] Instalar Socket.io en ambos servidores
- [ ] Configurar Socket.io server en Node.js
- [ ] Configurar Socket.io client en FastAPI
- [ ] Implementar eventos de nuevas señales
- [ ] Implementar eventos de trades ejecutados
- [ ] Actualizar Dashboard para escuchar eventos
- [ ] Implementar auto-refresh de datos
- [ ] Agregar notificaciones toast

**Entregables**:
```typescript
// web/server/_core/socket.ts
import { Server } from 'socket.io';
import { Server as HttpServer } from 'http';

export function setupSocketIO(httpServer: HttpServer) {
  const io = new Server(httpServer, {
    cors: {
      origin: process.env.CLIENT_URL || 'http://localhost:5173',
      credentials: true
    }
  });

  io.on('connection', (socket) => {
    console.log('Client connected:', socket.id);
    
    socket.on('subscribe', (userId: number) => {
      socket.join(`user:${userId}`);
    });

    socket.on('disconnect', () => {
      console.log('Client disconnected:', socket.id);
    });
  });

  return io;
}

// Función para emitir eventos
export function emitToUser(io: Server, userId: number, event: string, data: any) {
  io.to(`user:${userId}`).emit(event, data);
}
```

```python
# api/utils/socket_client.py
import socketio

sio = socketio.AsyncClient()

async def connect_to_websocket():
    await sio.connect('http://localhost:3000')

async def emit_new_signal(user_id: int, signal_data: dict):
    await sio.emit('new_signal', {
        'userId': user_id,
        'signal': signal_data
    })

async def emit_trade_executed(user_id: int, trade_data: dict):
    await sio.emit('trade_executed', {
        'userId': user_id,
        'trade': trade_data
    })
```

**Archivos a Crear**:
- `web/server/_core/socket.ts`
- `api/utils/socket_client.py`
- `web/client/src/hooks/useWebSocket.ts`

**Archivos a Modificar**:
- `web/server/_core/index.ts` (inicializar Socket.io)
- `api/main.py` (emitir eventos al procesar señales)
- `web/client/src/pages/Dashboard.tsx` (escuchar eventos)
- `web/client/src/pages/Signals.tsx` (escuchar eventos)

**Criterios de Aceptación**:
- ✅ WebSocket se conecta correctamente
- ✅ Nuevas señales aparecen automáticamente en UI
- ✅ Trades ejecutados se reflejan en tiempo real
- ✅ Notificaciones toast funcionan
- ✅ Reconexión automática funciona

---

#### 3.4 Implementación de PnL Real (4 días)

**Responsable**: Backend Developer + Full-stack Developer  
**Prioridad**: 🟡 Alta

**Actividades**:
- [ ] Crear servicio de cálculo de PnL en tiempo real
- [ ] Implementar fetching de precios actuales con CCXT
- [ ] Calcular PnL para trades abiertos
- [ ] Actualizar Dashboard con PnL en tiempo real
- [ ] Agregar gráfico de evolución de PnL
- [ ] Implementar caché de precios (actualizar cada 30s)

**Entregables**:
```typescript
// web/server/services/pnlCalculator.ts
import ccxt from 'ccxt';

export async function calculateRealTimePnL(trades: Trade[]): Promise<Trade[]> {
  const exchanges = new Map<string, ccxt.Exchange>();
  
  for (const trade of trades) {
    if (trade.status !== 'filled') continue;
    
    // Obtener exchange
    let exchange = exchanges.get(trade.marketType);
    if (!exchange) {
      exchange = new ccxt.binance(); // Default
      exchanges.set(trade.marketType, exchange);
    }
    
    // Obtener precio actual
    const ticker = await exchange.fetchTicker(trade.symbol);
    const currentPrice = ticker.last;
    
    // Calcular PnL
    if (trade.side === 'BUY') {
      trade.pnl = (currentPrice - trade.price) * trade.amount;
    } else {
      trade.pnl = (trade.price - currentPrice) * trade.amount;
    }
  }
  
  return trades;
}
```

**Archivos a Crear**:
- `web/server/services/pnlCalculator.ts`

**Archivos a Modificar**:
- `web/server/routers.ts` (actualizar getTrades para incluir PnL real)
- `web/client/src/pages/Dashboard.tsx` (mostrar PnL actualizado)

**Criterios de Aceptación**:
- ✅ PnL se calcula con precios actuales
- ✅ Dashboard muestra PnL en tiempo real
- ✅ Caché de precios funciona
- ✅ Performance es aceptable (< 2s para cargar)

---

### 📊 Métricas de Éxito - Sprint 3

| Métrica | Objetivo | Medición |
|---------|----------|----------|
| Backtest funcional | 100% | Usa API real |
| Señales en tiempo real | < 2s | Latencia de notificación |
| PnL accuracy | > 99% | Comparado con exchange |
| WebSocket uptime | > 99.5% | Disponibilidad |

---

## 🟥 Sprint 4: Ejecución Real y Hardening

**Duración**: 3 semanas  
**Objetivo**: Habilitar el trading con fondos reales y asegurar la estabilidad del sistema.

### 📌 Tareas Principales

#### 4.1 Habilitación de CEX Real (5 días)

**Responsable**: Backend Developer  
**Prioridad**: 🔴 Crítica

**Actividades**:
- [ ] Configurar cuentas de testnet (Binance Testnet, Bybit Testnet)
- [ ] Descomentar lógica de `create_order` en CEXService
- [ ] Implementar validación de saldo antes de ejecutar
- [ ] Agregar confirmación de órdenes
- [ ] Implementar logging detallado de órdenes
- [ ] Testear con órdenes pequeñas en testnet
- [ ] Implementar switch demo/real en configuración

**Entregables**:
```python
# api/services/cex_service.py - Actualizado
async def execute_trade(self, analysis: AnalysisResult, user_id: int, signal_id: int) -> ExecutionResult:
    # Obtener configuración del usuario
    config = await get_user_config(user_id)
    
    if config.demo_mode:
        return await self._execute_demo_trade(analysis, user_id, signal_id)
    else:
        return await self._execute_real_trade(analysis, user_id, signal_id, config)

async def _execute_real_trade(self, analysis: AnalysisResult, user_id: int, signal_id: int, config):
    try:
        symbol = analysis.symbol
        side = analysis.decision.lower()
        amount = analysis.parameters.get('amount', 0)
        
        # Validar saldo
        balance = self.exchange.fetch_balance()
        if side == 'buy':
            required = amount * self.exchange.fetch_ticker(symbol)['last']
            available = balance['USDT']['free']
            if required > available:
                return ExecutionResult(success=False, message="Saldo insuficiente")
        
        # Ejecutar orden REAL
        logger.info(f"[REAL] Ejecutando {side} {amount} {symbol} para usuario {user_id}")
        order = self.exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=amount
        )
        
        # Guardar en DB
        db = SessionLocal()
        trade = Trade(
            user_id=user_id,
            signal_id=signal_id,
            symbol=symbol,
            side=side.upper(),
            price=order['average'],
            amount=amount,
            market_type="CEX",
            is_demo=False,
            order_id=order['id'],
            status='filled'
        )
        db.add(trade)
        db.commit()
        db.close()
        
        return ExecutionResult(
            success=True,
            message=f"Orden ejecutada: {order['id']}"
        )
        
    except Exception as e:
        logger.error(f"Error ejecutando trade real: {e}")
        return ExecutionResult(success=False, message=str(e))
```

**Archivos a Modificar**:
- `api/services/cex_service.py` (habilitar ejecución real)
- `api/config.py` (agregar TESTNET_MODE)
- `web/drizzle/schema.ts` (asegurar campo demoMode en app_config)

**Criterios de Aceptación**:
- ✅ Órdenes se ejecutan en testnet exitosamente
- ✅ Validación de saldo funciona
- ✅ Órdenes se guardan en DB con order_id
- ✅ Switch demo/real funciona en UI
- ✅ Logging detallado de todas las órdenes

---

#### 4.2 Firma de Transacciones DEX (6 días)

**Responsable**: Backend Developer  
**Prioridad**: 🔴 Crítica

**Actividades**:
- [ ] Instalar librerías de Solana (`solana-py`)
- [ ] Implementar firma de transacciones con private key
- [ ] Integrar con Jupiter Aggregator para swaps
- [ ] Implementar estimación de gas/fees
- [ ] Agregar validación de slippage
- [ ] Testear en Solana Devnet
- [ ] Implementar para EVM (opcional)

**Entregables**:
```python
# api/services/dex_service.py - Actualizado
from solana.rpc.api import Client
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
import base58

async def execute_trade(self, analysis: AnalysisResult, user_id: int, signal_id: int) -> ExecutionResult:
    config = await get_user_config(user_id)
    
    if config.demo_mode:
        return await self._execute_demo_trade(analysis, user_id, signal_id)
    else:
        return await self._execute_real_dex_trade(analysis, user_id, signal_id, config)

async def _execute_real_dex_trade(self, analysis: AnalysisResult, user_id: int, signal_id: int, config):
    try:
        # Conectar a Solana
        client = Client(config.solana_rpc_url or "https://api.devnet.solana.com")
        
        # Cargar wallet
        private_key_bytes = base58.b58decode(config.dex_wallet_private_key)
        wallet = Keypair.from_bytes(private_key_bytes)
        
        # Obtener cotización de Jupiter
        symbol = analysis.symbol
        amount = analysis.parameters.get('amount', 0.1)
        
        # Construir transacción de swap
        # (Aquí iría la lógica específica de Jupiter/Raydium)
        
        # Firmar y enviar transacción
        transaction = Transaction()
        # ... agregar instrucciones
        
        signature = client.send_transaction(transaction, wallet)
        
        # Confirmar transacción
        client.confirm_transaction(signature)
        
        # Guardar en DB
        db = SessionLocal()
        trade = Trade(
            user_id=user_id,
            signal_id=signal_id,
            symbol=symbol,
            side=analysis.decision,
            price=0.0,  # Obtener del resultado
            amount=amount,
            market_type="DEX",
            is_demo=False,
            order_id=str(signature),
            status='filled'
        )
        db.add(trade)
        db.commit()
        db.close()
        
        return ExecutionResult(
            success=True,
            message=f"Transacción DEX ejecutada: {signature}"
        )
        
    except Exception as e:
        logger.error(f"Error ejecutando trade DEX: {e}")
        return ExecutionResult(success=False, message=str(e))
```

**Archivos a Modificar**:
- `api/services/dex_service.py` (implementar firma de transacciones)
- `api/requirements.txt` (agregar `solana`, `solders`)
- `api/config.py` (agregar SOLANA_RPC_URL)

**Criterios de Aceptación**:
- ✅ Transacciones se firman correctamente
- ✅ Swaps se ejecutan en Devnet
- ✅ Slippage se valida antes de ejecutar
- ✅ Fees se estiman correctamente
- ✅ Transacciones se guardan en DB

---

#### 4.3 Gestión de Errores (Circuit Breaker) (4 días)

**Responsable**: Backend Developer  
**Prioridad**: 🟡 Alta

**Actividades**:
- [ ] Implementar patrón Circuit Breaker
- [ ] Agregar retry logic con exponential backoff
- [ ] Implementar manejo de rate limits
- [ ] Agregar fallback strategies
- [ ] Implementar health checks de exchanges
- [ ] Agregar alertas de errores críticos

**Entregables**:
```python
# api/utils/circuit_breaker.py
from enum import Enum
import time
from typing import Callable, Any

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

# Uso en CEXService
circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=30)

async def execute_with_retry(self, func, *args, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await circuit_breaker.call(func, *args)
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            wait_time = 2 ** attempt  # Exponential backoff
            await asyncio.sleep(wait_time)
```

**Archivos a Crear**:
- `api/utils/circuit_breaker.py`
- `api/utils/retry_handler.py`

**Archivos a Modificar**:
- `api/services/cex_service.py` (usar circuit breaker)
- `api/services/dex_service.py` (usar circuit breaker)

**Criterios de Aceptación**:
- ✅ Circuit breaker se abre después de 3 fallos
- ✅ Retry logic funciona con exponential backoff
- ✅ Rate limits se respetan
- ✅ Alertas se envían para errores críticos

---

#### 4.4 Finalización de UI/UX (5 días)

**Responsable**: Full-stack Developer  
**Prioridad**: 🟢 Media

**Actividades**:
- [ ] Pulir diseño de tablas de historial
- [ ] Mejorar indicadores de confianza de IA
- [ ] Agregar tooltips explicativos
- [ ] Implementar modo oscuro (si no existe)
- [ ] Optimizar performance de renders
- [ ] Agregar animaciones sutiles
- [ ] Implementar skeleton loaders
- [ ] Realizar testing de usabilidad

**Entregables**:
- UI pulida y profesional
- Documentación de componentes
- Guía de estilo actualizada

**Archivos a Modificar**:
- `web/client/src/pages/*.tsx` (todos los componentes)
- `web/client/src/components/*.tsx` (componentes reutilizables)
- `web/client/src/index.css` (estilos globales)

**Criterios de Aceptación**:
- ✅ Diseño es consistente en todas las páginas
- ✅ Indicadores de confianza son claros
- ✅ Performance es óptima (< 100ms TTI)
- ✅ Accesibilidad cumple estándares WCAG 2.1

---

### 📊 Métricas de Éxito - Sprint 4

| Métrica | Objetivo | Medición |
|---------|----------|----------|
| Órdenes ejecutadas | > 95% | Tasa de éxito |
| Tiempo de ejecución | < 3s | Desde señal hasta orden |
| Circuit breaker | Funcional | Se abre/cierra correctamente |
| Satisfacción UI | > 8/10 | Feedback de usuarios |

---

## 📈 Roadmap Visual

```mermaid
gantt
    title Plan de Implementación - SignalKey Platform
    dateFormat YYYY-MM-DD
    section Sprint 1
    Migración de Esquema           :s1-1, 2026-01-20, 3d
    Refactor Persistencia Python   :s1-2, 2026-01-23, 4d
    Sincronización de Modelos      :s1-3, 2026-01-27, 2d
    Configuración de Entorno       :s1-4, 2026-01-29, 2d
    
    section Sprint 2
    Middleware Auth FastAPI        :s2-1, 2026-02-03, 3d
    Encriptación Credenciales      :s2-2, 2026-02-06, 4d
    Servicio Proxy Node            :s2-3, 2026-02-10, 3d
    Validación de Secrets          :s2-4, 2026-02-13, 2d
    
    section Sprint 3
    Conexión Backtest              :s3-1, 2026-02-17, 3d
    Refactor Señales               :s3-2, 2026-02-20, 5d
    Dashboard Tiempo Real          :s3-3, 2026-02-25, 6d
    PnL Real                       :s3-4, 2026-03-03, 4d
    
    section Sprint 4
    CEX Real                       :s4-1, 2026-03-10, 5d
    Firma Transacciones DEX        :s4-2, 2026-03-15, 6d
    Circuit Breaker                :s4-3, 2026-03-21, 4d
    Finalización UI/UX             :s4-4, 2026-03-25, 5d
```

---

## 🎯 Definición de "Done"

Para considerar cada sprint completado, se deben cumplir los siguientes criterios:

### Sprint 1 - Done
- [ ] Todos los datos migrados de SQLite a MySQL
- [ ] API Python conecta exitosamente a MySQL
- [ ] Tests de integración pasan al 100%
- [ ] Documentación actualizada
- [ ] Code review aprobado

### Sprint 2 - Done
- [ ] Todos los endpoints protegidos con JWT
- [ ] Credenciales encriptadas en DB
- [ ] Proxy funciona correctamente
- [ ] Validación de credenciales implementada
- [ ] Tests de seguridad pasan
- [ ] Penetration testing básico completado

### Sprint 3 - Done
- [ ] Backtest conectado a API real
- [ ] Señales se guardan en MySQL
- [ ] WebSocket funciona en tiempo real
- [ ] PnL se calcula correctamente
- [ ] Tests end-to-end pasan
- [ ] Performance benchmarks cumplidos

### Sprint 4 - Done
- [ ] Órdenes reales ejecutadas en testnet
- [ ] Transacciones DEX firmadas correctamente
- [ ] Circuit breaker funciona
- [ ] UI/UX pulida y aprobada
- [ ] Tests de carga pasan
- [ ] Documentación de usuario completa
- [ ] Sistema listo para producción

---

## 🚨 Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Pérdida de datos en migración | Media | Alto | Backup completo antes de migrar, validación exhaustiva |
| Problemas de performance con MySQL | Baja | Medio | Indexar correctamente, usar caché, monitoring |
| Fallas en exchanges (rate limits) | Alta | Medio | Circuit breaker, retry logic, múltiples exchanges |
| Bugs en ejecución real | Media | Crítico | Testing extensivo en testnet, límites de monto |
| Problemas de seguridad | Media | Crítico | Auditoría de seguridad, encriptación, auth robusto |
| Retrasos en desarrollo | Media | Medio | Buffer de tiempo, priorización clara |

---

## 📚 Recursos Necesarios

### Infraestructura
- [ ] Servidor MySQL (AWS RDS o similar)
- [ ] Servidor de producción (2 instancias: Node.js + Python)
- [ ] Redis para caché (opcional pero recomendado)
- [ ] Monitoring (Datadog, New Relic, o similar)
- [ ] Logging centralizado (ELK Stack o similar)

### Cuentas de Exchange
- [ ] Binance Testnet
- [ ] Bybit Testnet
- [ ] OKX Testnet (opcional)
- [ ] Solana Devnet (para DEX)

### APIs y Servicios
- [ ] Google Gemini API (ya existente)
- [ ] GMGN API (ya existente)
- [ ] Telegram Bot (ya existente)
- [ ] Socket.io (a instalar)

### Herramientas de Desarrollo
- [ ] Git/GitHub
- [ ] Docker
- [ ] Postman/Insomnia (testing de APIs)
- [ ] MySQL Workbench
- [ ] VS Code con extensiones

---

## 📞 Comunicación y Reportes

### Daily Standups
- **Frecuencia**: Diario
- **Duración**: 15 minutos
- **Formato**: ¿Qué hice ayer? ¿Qué haré hoy? ¿Impedimentos?

### Sprint Reviews
- **Frecuencia**: Al final de cada sprint
- **Duración**: 1 hora
- **Participantes**: Todo el equipo + stakeholders
- **Objetivo**: Demo de funcionalidades completadas

### Sprint Retrospectives
- **Frecuencia**: Al final de cada sprint
- **Duración**: 45 minutos
- **Participantes**: Equipo de desarrollo
- **Objetivo**: Identificar mejoras para el próximo sprint

### Reportes Semanales
- **Formato**: Documento escrito
- **Contenido**: 
  - Progreso vs plan
  - Blockers
  - Próximos pasos
  - Métricas clave

---

## ✅ Checklist de Inicio

Antes de comenzar el Sprint 1, asegúrate de tener:

- [ ] Acceso a todos los repositorios
- [ ] Credenciales de bases de datos
- [ ] Acceso a servicios cloud
- [ ] Herramientas de desarrollo instaladas
- [ ] Equipo completo asignado
- [ ] Backlog priorizado
- [ ] Entorno de desarrollo configurado
- [ ] Plan aprobado por stakeholders

---

## 🎓 Conclusión

Este plan de implementación proporciona una ruta clara y estructurada para integrar la API Python con la aplicación web, transformando dos sistemas independientes en una plataforma cohesiva de trading automatizado.

**Puntos Clave**:
- ✅ Enfoque incremental y de bajo riesgo
- ✅ Priorización de seguridad desde el principio
- ✅ Métricas claras de éxito
- ✅ Mitigación proactiva de riesgos
- ✅ Flexibilidad para ajustes

**Próximo Paso**: Revisar y aprobar este plan, luego comenzar con el Sprint 1.

---

**Fecha de Última Actualización**: 16 de Enero de 2026  
**Versión**: 1.0  
**Estado**: Pendiente de Aprobación
