# Plan de Migración a MongoDB - SignalKey Platform

## 1. Esquema de Colecciones

### Colección: `users`
- `_id`: ObjectId
- `openId`: String (Unique)
- `name`: String
- `email`: String
- `role`: String ("user", "admin")
- `createdAt`: Date
- `updatedAt`: Date
- `lastSignedIn`: Date

### Colección: `app_configs`
- `_id`: ObjectId
- `userId`: ObjectId (Ref: users)
- `demoMode`: Boolean
- `geminiApiKey`: String
- `gmgnApiKey`: String
- `telegramBotToken`: String
- `telegramChatId`: String (Nuevo)
- `exchanges`: Array de Objetos
  - `exchangeId`: String (e.g., "binance")
  - `apiKey`: String
  - `secret`: String
  - `password`: String
  - `uid`: String
  - `isActive`: Boolean
- `dexConfig`: Objeto
  - `walletPrivateKey`: String
  - `rpcUrl`: String
- `investmentLimits`: Objeto
  - `cexMaxAmount`: Float
  - `dexMaxAmount`: Float
- `createdAt`: Date
- `updatedAt`: Date

### Colección: `trading_signals`
- `_id`: ObjectId
- `userId`: ObjectId (Ref: users)
- `source`: String
- `rawText`: String
- `decision`: String
- `symbol`: String
- `marketType`: String
- `confidence`: Float
- `reasoning`: String
- `status`: String
- `createdAt`: Date

### Colección: `trades`
- `_id`: ObjectId
- `userId`: ObjectId (Ref: users)
- `signalId`: ObjectId (Ref: trading_signals)
- `symbol`: String
- `side`: String
- `price`: Float
- `amount`: Float
- `marketType`: String
- `isDemo`: Boolean
- `orderId`: String
- `status`: String
- `pnl`: Float
- `createdAt`: Date
- `executedAt`: Date

### Colección: `virtual_balances`
- `_id`: ObjectId
- `userId`: ObjectId (Ref: users)
- `marketType`: String
- `asset`: String
- `amount`: Float
- `updatedAt`: Date

## 2. Cambios en la API (Python)
- Reemplazar `SQLAlchemy` con `Motor` (driver asíncrono para MongoDB) o `PyMongo`.
- Actualizar `api/models/database.py` para manejar la conexión a MongoDB.
- Refactorizar `api/config.py` para que lea de la base de datos en lugar de `.env` (excepto la URI de MongoDB).

## 3. Cambios en el Servidor Web (Node.js)
- Reemplazar `Drizzle` con `Mongoose` o el driver nativo de MongoDB.
- Actualizar `web/server/db.ts` para usar MongoDB.
- Actualizar esquemas y tipos en `web/shared/types.ts`.

## 4. Estrategia de Implementación
1. Instalar dependencias necesarias (`motor`, `pymongo` para Python; `mongoose` para Node.js).
2. Crear los nuevos modelos en la API.
3. Crear los nuevos modelos en el servidor web.
4. Refactorizar los servicios de la API para inyectar la configuración desde la DB.
5. Actualizar la UI para permitir la edición de los nuevos campos (límites de inversión, múltiples exchanges).
