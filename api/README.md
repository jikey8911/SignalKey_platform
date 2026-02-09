# Crypto Trading Bot API

Este proyecto implementa una API en Python utilizando FastAPI para automatizar operaciones de trading de criptomonedas. La API es capaz de recibir señales de trading a través de un bot de Telegram o webhooks, analizar estas señales utilizando la inteligencia artificial de Gemini, y ejecutar operaciones en exchanges centralizados (CEX) a través de CCXT o en exchanges descentralizados (DEX) a través de la API de GMGN.

## Características

*   **Recepción de Señales**: Soporte para señales de trading vía bot de Telegram y webhooks HTTP.
*   **Análisis Inteligente**: Utiliza la API de Gemini para analizar las señales y tomar decisiones de trading (BUY/SELL/HOLD), incluyendo la extracción de parámetros como el símbolo, tipo de mercado, cantidad, Take Profit (TP) y Stop Loss (SL).
*   **Ejecución en CEX**: Integración con la librería CCXT para interactuar con múltiples exchanges centralizados.
*   **Ejecución en DEX**: Integración con la API de GMGN para operaciones en exchanges descentralizados.
*   **Modo Demo (Paper Trading)**: Permite simular operaciones con señales reales utilizando un balance virtual (CEX: 10,000 USDT, DEX: 100 SOL por defecto).
*   **Backtesting**: Módulo para probar estrategias con datos históricos de mercado.
*   **Base de Datos Local**: Registro de historial de trades y balances virtuales mediante SQLite.
*   **Modular y Escalable**: Arquitectura diseñada para facilitar la adición de nuevas funcionalidades y el mantenimiento.

## Estructura del Proyecto

```
crypto_bot_api/
├── main.py
├── config.py
├── requirements.txt
├── .env.example
├── api/
│   └── __init__.py
├── bot/
│   └── telegram_bot.py
├── models/
│   └── schemas.py
├── services/
│   ├── __init__.py
│   ├── gemini_service.py
│   ├── cex_service.py
│   └── dex_service.py
└── utils/
    └── __init__.py
```

## Configuración del Entorno

1.  **Clonar el Repositorio**:

    ```bash
    git clone <URL_DEL_REPOSITORIO>
    cd crypto_bot_api
    ```

2.  **Crear y Activar Entorno Virtual** (recomendado):

    ```bash
    python3.11 -m venv venv
    source venv/bin/activate
    ```

3.  **Instalar Dependencias**:

    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar Variables de Entorno**:

    Copia el archivo `.env.example` a `.env` y edítalo con tus credenciales:

    ```bash
    cp .env.example .env
    ```

    Asegúrate de configurar las siguientes variables:

    *   `GEMINI_API_KEY`: Tu clave API de Google Gemini. Puedes obtenerla en [Google AI Studio](https://aistudio.google.com/app/apikey).
    *   `TELEGRAM_BOT_TOKEN`: El token de tu bot de Telegram. Obténlo de [@BotFather](https://t.me/botfather).
    *   `GMGN_API_KEY`: Tu clave API de GMGN.ai (requiere aprobación basada en volumen de trading).
    *   `EXCHANGE_ID`: El ID del exchange CEX que deseas usar (ej. `okx`, `bybit`).
    *   `CEX_API_KEY`, `CEX_SECRET`: Tus credenciales API para el exchange CEX.
    *   `CEX_PASSWORD`: La contraseña o passphrase de la API (necesaria para exchanges como OKX o KuCoin).
    *   `CEX_UID`: Tu ID de usuario en el exchange (si es requerido).
    *   `DEX_WALLET_PRIVATE_KEY`: La clave privada de tu wallet para operaciones DEX. **¡ADVERTENCIA: MANEJA ESTO CON EXTREMA PRECAUCIÓN! NO LA EXPONGAS PÚBLICAMENTE.**
    *   `SOLANA_RPC_URL`: URL de un nodo RPC de Solana (o la red DEX que uses).

## Uso

### Iniciar la API Principal

Para iniciar el servidor FastAPI:

```bash
python3.11 main.py
```

La API se ejecutará en `http://0.0.0.0:8000` (o el puerto configurado en `.env`). Puedes verificar su estado en `http://0.0.0.0:8000/health`.

### Funciones de Simulación y Backtesting

*   **Consultar Balance Demo**: `GET /demo/balance`
*   **Consultar Historial Demo**: `GET /demo/history`
*   **Ejecutar Backtest**: `GET /backtest/{symbol}?days=7` (Ejemplo: `/backtest/BTC-USDT?days=30`)

### Iniciar el Bot de Telegram

En una terminal separada, inicia el bot de Telegram:

```bash
python3.11 bot/telegram_bot.py
```

El bot comenzará a escuchar mensajes en Telegram. Cualquier mensaje de texto que reciba (que no sea un comando) será enviado a la API principal para su análisis.

### Envío de Señales (Webhooks)

Puedes enviar señales a la API principal a través del endpoint `/webhook/signal` usando una solicitud POST. El cuerpo de la solicitud debe ser un JSON que cumpla con el esquema `TradingSignal`:

**URL**: `http://0.0.0.0:8000/webhook/signal`
**Método**: `POST`
**Headers**: `Content-Type: application/json`

**Cuerpo de la Solicitud (JSON)**:

```json
{
  "source": "my_custom_webhook",
  "raw_text": "BUY BTC/USDT at market, TP 30000, SL 28000, amount 0.001",
  "metadata": {
    "alert_id": "12345",
    "priority": "high"
  }
}
```

La API procesará la señal en segundo plano y devolverá un estado de recepción.

## Flujo de Trabajo

1.  Una señal de trading es recibida por el bot de Telegram o el endpoint de webhook.
2.  La señal se envía a la API principal (`main.py`).
3.  La API utiliza `GeminiService` para analizar el `raw_text` de la señal. Gemini AI devuelve una decisión (BUY/SELL/HOLD), el símbolo, tipo de mercado y parámetros de la operación.
4.  Si la decisión no es HOLD, la API determina si la operación es para CEX o DEX.
5.  Para CEX, `CEXService` utiliza CCXT para ejecutar la orden (actualmente simulado).
6.  Para DEX, `DEXService` utiliza la API de GMGN para ejecutar la orden (actualmente simulado, requiere implementación de firma de transacciones).
7.  Los resultados de la ejecución se registran.

## Consideraciones de Seguridad

*   **Claves Privadas**: Nunca expongas tu `DEX_WALLET_PRIVATE_KEY` o `CEX_SECRET` en código fuente o logs. Utiliza variables de entorno y asegúrate de que tu archivo `.env` no sea versionado en sistemas de control de versiones públicos.
*   **Slippage y Gestión de Riesgos**: La implementación actual es básica. En un entorno de producción, es crucial añadir una gestión robusta de slippage, límites de riesgo, y validación de órdenes.
*   **Simulación vs. Real**: Las funciones de ejecución de órdenes en `cex_service.py` y `dex_service.py` están actualmente simuladas. Para operaciones reales, deberás descomentar y completar la lógica de `create_order` en CCXT y la lógica de firma/envío de transacciones en GMGN.

## Próximos Pasos (Mejoras Potenciales)

*   Implementación completa de la firma y envío de transacciones DEX con GMGN.
*   Añadir manejo de errores más granular y reintentos para operaciones de trading.
*   Integrar una base de datos para registrar el historial de señales, análisis y operaciones.
*   Desarrollar una interfaz de usuario web para monitoreo y gestión.
*   Implementar estrategias de gestión de riesgo (tamaño de posición, stop dinámico).
*   Soporte para múltiples bots de Telegram o canales.

---

**Autor**: Manus AI
**Fecha**: 12 de Enero de 2026
