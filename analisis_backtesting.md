Claro, aquí tienes un resumen en español del funcionamiento del sistema de backtesting, conectando la `api` con la `web`.

### Flujo General

El sistema de backtesting permite a los usuarios simular estrategias de trading sobre datos históricos para evaluar su rendimiento antes de arriesgar capital real. El proceso involucra dos componentes principales: el **frontend (web)**, donde el usuario interactúa, y el **backend (api)**, que realiza todos los cálculos.

El flujo es el siguiente:

1.  **Configuración en la Web:** El usuario accede a la página de "Backtesting" en la aplicación web.
2.  **Llamada a la API:** La web solicita al backend los datos necesarios para los menús de configuración (exchanges, mercados, símbolos y modelos de IA disponibles).
3.  **Ejecución del Backtest:** El usuario selecciona sus parámetros (ej. `BTC/USDT`, 1 hora, 30 días) y pulsa "Ejecutar". La web envía esta configuración al backend.
4.  **Procesamiento en la API:** El backend recibe la petición, obtiene los datos históricos del mercado, y simula la estrategia elegida (ej. cruce de medias móviles, una estrategia de IA, o un "torneo" entre varias).
5.  **Visualización de Resultados:** La API devuelve un informe completo (rentabilidad, número de operaciones, etc.). La web lo recibe y lo muestra al usuario con gráficos y estadísticas detalladas.

---

### @web (Frontend - `web/client/src/pages/Backtest.tsx`)

Esta es la interfaz de usuario construida en React. Sus responsabilidades son:

-   **Formulario de Configuración:**
    -   Permite al usuario elegir un **Exchange** (ej. Binance), un **Mercado** (ej. SPOT) y un **Símbolo** (ej. BTC/USDT).
    -   Ofrece opciones para el **Timeframe** (1h, 4h, etc.) y el número de **días históricos** a analizar.
    -   Muestra el **Balance Virtual** del usuario (ej. $10,000 USDT) que se usará como capital inicial en la simulación.
    -   Permite seleccionar una **estrategia**, que puede ser simple o basada en un modelo de IA entrenado.

-   **Comunicación con la API:**
    -   Al pulsar "Ejecutar Backtesting", se realiza una llamada `POST` al endpoint `/api/backtest/run`.
    -   En esta llamada se envían todos los parámetros que el usuario seleccionó.

-   **Visualización de Resultados:**
    -   Muestra métricas clave como **Retorno Total (%)**, **Win Rate (%)** y **Max Drawdown (%)**.
    -   Renderiza un **gráfico de velas** donde se superponen marcadores de **COMPRA (BUY)** y **VENTA (SELL)**, permitiendo al usuario ver visualmente dónde la estrategia habría operado.
    -   Si el resultado es bueno, ofrece un botón para **"Crear Bot con esta Estrategia"**, que automatizaría la estrategia en modo simulación.

---

### @api (Backend - `routers/backtest_router.py` y `services/backtest_service.py`)

Esta es la lógica del servidor construida en FastAPI. Sus responsabilidades son:

-   **Endpoints (`backtest_router.py`):**
    -   `/run`: Es el endpoint principal. Recibe la configuración de la web, llama al `BacktestService` para hacer el trabajo pesado, y devuelve los resultados.
    -   `/exchanges`, `/markets`, `/symbols`: Proveen la información para rellenar los selectores en la interfaz de usuario.
    -   `/ml_models`: Devuelve la lista de modelos de IA que el usuario puede seleccionar.
    -   `/deploy_bot`: Crea una entrada en la base de datos para un nuevo bot simulado.

-   **Lógica del Servicio (`backtest_service.py`):**
    -   **Obtención de Datos:** Usa la librería `ccxt` para descargar los datos históricos de precios (OHLCV) del exchange y símbolo solicitados.
    -   **Simulación:** Itera sobre los datos históricos vela por vela. En cada paso, aplica la lógica de la estrategia seleccionada:
        -   **`_run_sma_backtest`:** Una estrategia simple que genera señales de compra/venta cuando dos medias móviles se cruzan.
        -   **`_run_ai_backtest`:** Usa un `AIAdapter` para enviar el contexto del mercado a un modelo de lenguaje (como Gemini) y pedirle una decisión (`BUY`, `SELL`, `HOLD`).
        -   **`_run_strategy_tournament`:** Ejecuta varias estrategias a la vez (SMA, AI-standard, AI-sniper) y las compara para recomendar la mejor según una puntuación que combina rentabilidad y fiabilidad.
    -   **Cálculo de Métricas:** Una vez simuladas todas las operaciones, calcula el beneficio/pérdida final, el porcentaje de aciertos (win rate), la peor racha (max drawdown) y otras estadísticas clave.
    -   **Gestión de Balance:** Antes de empezar, obtiene el balance virtual del usuario desde la base de datos (MongoDB) para usarlo como capital inicial.

En resumen, la **web** es la cara visible y el centro de control, mientras que la **api** es el motor de cálculo que realiza el trabajo duro de simulación y análisis.