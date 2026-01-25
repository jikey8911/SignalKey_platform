# Resumen de Refactorización: SignalKey Platform

Se ha completado la migración de la base de datos de SQLite/MySQL a **MongoDB** y se ha refactorizado la arquitectura para soportar configuraciones dinámicas y multi-usuario.

## Cambios Principales

### 1. Base de Datos (MongoDB)
- Se ha reemplazado la persistencia basada en SQL por **MongoDB**.
- **API (Python):** Implementado `api/models/mongodb.py` usando el driver asíncrono `motor`.
- **Web (Node.js):** Implementado `web/server/mongodb.ts` usando `mongoose`.

### 2. Configuraciones Dinámicas
- Se han eliminado las dependencias de variables de entorno (`.env`) para configuraciones operativas.
- **Exchanges:** Ahora se pueden configurar múltiples exchanges (Binance, OKX, KuCoin, etc.) desde la interfaz web.
- **Telegram:** El token del bot y el Chat ID se guardan en la base de datos, permitiendo que cada usuario tenga su propio bot.
- **Límites de Inversión:** Se han añadido campos específicos para definir el monto máximo a invertir en CEX (USDT) y DEX (SOL).

### 3. Refactorización de Servicios
- **CEXService:** Ahora recupera las credenciales del exchange activo directamente de MongoDB antes de cada operación. Valida el límite de inversión configurado.
- **DEXService:** Integrado con la configuración de MongoDB para usar la Private Key y el límite de inversión dinámico.
- **TelegramBotManager:** Nuevo gestor que puede iniciar y sincronizar múltiples bots basados en los tokens almacenados en la base de datos.

### 4. Interfaz de Usuario (Settings)
- La página de **Settings** ha sido rediseñada para permitir:
  - Gestión de múltiples exchanges (Añadir/Eliminar/Activar).
  - Configuración de límites de inversión diferenciados para CEX y DEX.
  - Configuración de API Keys de Gemini y GMGN.
  - Switch para activar/desactivar el Modo Demo.

## Instrucciones de Ejecución

### Requisitos
- MongoDB 7.0+ instalado y corriendo.
- Python 3.11+ con dependencias (`motor`, `pymongo`, `ccxt`, `fastapi`).
- Node.js con `pnpm`.

### Iniciar API
```bash
cd api
export PYTHONPATH=$PYTHONPATH:.
python3 main.py
```

### Iniciar Web
```bash
cd web
pnpm dev
```
