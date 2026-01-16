# SignalKey Trading API

API Python con FastAPI para recibir señales de trading, analizarlas con Gemini AI y ejecutarlas en exchanges centralizados (CEX) y descentralizados (DEX).

## Características

- ✅ Recepción de señales vía Telegram Bot o Webhooks
- ✅ Análisis inteligente con Google Gemini AI
- ✅ Ejecución en CEX (Binance, OKX, KuCoin, Bybit, etc) vía CCXT
- ✅ Ejecución en DEX (Solana) vía GMGN API
- ✅ Modo Demo para pruebas sin riesgo (paper trading)
- ✅ Backtesting con datos históricos
- ✅ Soporte para múltiples exchanges y parámetros de credenciales
- ✅ Logging completo y manejo de errores

## Requisitos

- Python 3.11+
- pip o pip3

## Instalación

1. **Clonar el repositorio**
```bash
git clone https://github.com/jikey8911/SignalKey_platform.git
cd SignalKey_platform/api
```

2. **Crear entorno virtual**
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
cp .env.example .env
# Edita .env con tus API Keys
```

## Configuración de API Keys

### Gemini AI
1. Accede a [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Crea una nueva API Key
3. Copia el valor en `GEMINI_API_KEY`

### GMGN (DEX)
1. Accede a [GMGN.ai](https://gmgn.ai)
2. Obtén tu API Key
3. Copia el valor en `GMGN_API_KEY`

### Telegram Bot
1. Abre [@BotFather](https://t.me/BotFather) en Telegram
2. Crea un nuevo bot con `/newbot`
3. Copia el token en `TELEGRAM_BOT_TOKEN`

### Exchange (CEX)
Dependiendo del exchange que uses:

**Binance:**
- Accede a [Binance API Management](https://www.binance.com/en/account/api-management)
- Crea una nueva API Key
- Copia `API Key` en `CEX_API_KEY`
- Copia `Secret Key` en `CEX_API_SECRET`

**OKX:**
- Accede a [OKX API Management](https://www.okx.com/account/my-api)
- Crea una nueva API Key
- Copia `API Key` en `CEX_API_KEY`
- Copia `Secret Key` en `CEX_API_SECRET`
- Copia `Passphrase` en `CEX_PASSWORD`
- Copia `UID` en `CEX_UID`

**KuCoin:**
- Similar a OKX, requiere API Key, Secret y Passphrase

### DEX Wallet (Solana)
1. Crea una wallet en [Phantom](https://phantom.app/) o similar
2. Exporta tu private key
3. Copia en `DEX_WALLET_PRIVATE_KEY`
⚠️ **NUNCA compartas tu private key**

## Uso

### Iniciar el servidor
```bash
python main.py
```

El servidor estará disponible en `http://localhost:8000`

### Endpoints principales

**Health Check:**
```bash
curl http://localhost:8000/health
```

**Recibir Señal (Telegram):**
```bash
curl -X POST http://localhost:8000/webhook/telegram \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC-USDT", "side": "BUY", "market": "CEX"}'
```

**Recibir Señal (Genérica):**
```bash
curl -X POST http://localhost:8000/webhook/signal \
  -H "Content-Type: application/json" \
  -d '{"signal": "BUY BTC at 40000"}'
```

**Ejecutar Backtesting:**
```bash
curl -X POST "http://localhost:8000/backtest?symbol=BTC-USDT&days=30&timeframe=1h"
```

**Obtener Configuración:**
```bash
curl http://localhost:8000/config
```

## Modo Demo vs Real

### Modo Demo (DEMO_MODE=True)
- Las operaciones se simulan con balance virtual
- No se ejecutan órdenes reales
- Perfecto para pruebas y validación de estrategias
- Se registra todo en la base de datos local

### Modo Real (DEMO_MODE=False)
- Las operaciones se ejecutan en los exchanges reales
- ⚠️ REQUIERE credenciales válidas
- ⚠️ ARRIESGA CAPITAL REAL
- Usar solo después de validar en modo demo

## Estructura del Proyecto

```
api/
├── main.py                 # Servidor principal
├── config.py              # Configuración
├── requirements.txt       # Dependencias
├── .env.example          # Variables de entorno (ejemplo)
├── bot/                  # Módulo de Telegram Bot
├── services/             # Servicios (Gemini, CCXT, GMGN)
├── models/               # Modelos de datos
└── utils/                # Utilidades
```

## Flujo de Procesamiento de Señales

1. **Recepción**: Señal llega vía Telegram o Webhook
2. **Análisis**: Gemini AI analiza la señal y extrae parámetros
3. **Decisión**: Sistema decide si ejecutar o no
4. **Ejecución**: 
   - En modo demo: Simula la operación
   - En modo real: Ejecuta en el exchange
5. **Registro**: Guarda en base de datos
6. **Notificación**: Envía confirmación

## Troubleshooting

**Error: "GEMINI_API_KEY not found"**
- Verifica que hayas configurado correctamente el .env
- Asegúrate de que la API Key es válida

**Error: "Exchange not available"**
- Verifica que el exchange esté soportado por CCXT
- Comprueba las credenciales del exchange

**Error: "Invalid private key"**
- Verifica que el private key de Solana sea válido
- Asegúrate de que no tenga espacios o caracteres especiales

## Seguridad

- 🔒 Nunca commits .env con credenciales reales
- 🔒 Usa variables de entorno para secretos
- 🔒 Limita permisos de API Keys en exchanges
- 🔒 Usa IP whitelist en exchanges cuando sea posible
- 🔒 Revisa logs regularmente

## Soporte

Para reportar issues o sugerencias, abre un issue en el repositorio.

## Licencia

MIT
