# Informe de Análisis de Código: Bots, Backtest y Training

## 1. Bots (`api/src/application/services/bot_service.py`, `execution_engine.py`)

### Descripción del Funcionamiento
El sistema de Bots gestiona el ciclo de vida de estrategias automatizadas de trading.
- **SignalBotService:** Coordina la suscripción a datos de mercado (WebSockets) y la ejecución de la lógica de decisión.
- **ExecutionEngine:** Responsable de ejecutar las órdenes, ya sea en modo simulado (contra una base de datos local) o real (contra exchanges vía CCXT).
- **Flujo:** Los datos de mercado llegan -> Se actualiza un buffer -> Si cierra una vela, se ejecuta la IA -> Si hay señal, el Engine ejecuta la orden -> Se actualiza la posición en DB.

### Errores de Código y Lógica
1.  **Condición de Carrera en Simulación:** En `ExecutionEngine._update_simulation_position_db`, se lee la posición actual, se modifican valores en memoria y se guarda. Si dos señales llegan casi simultáneamente, se pueden perder actualizaciones. MongoDB soporta operaciones atómicas (`$inc`, `$set`) que deberían usarse.
2.  **Fail-Open en Validación de Saldo Simulado:** En `ExecutionEngine._check_risk_and_balance`, si ocurre una excepción al verificar el saldo simulado, el código retorna `True` (permite operar). Esto debería ser `False` para evitar estados inconsistentes.
3.  **Importaciones Circulares:** `SignalBotService` realiza importaciones dentro de métodos (`from api.src.adapters.driven.notifications.socket_service import socket_service`) para evitar ciclos. Esto indica un acoplamiento fuerte que debería resolverse con inyección de dependencias o eventos.
4.  **Iteración Ineficiente:** En `_handle_candle_update`, se itera sobre bots y se filtra por exchange dentro del bucle de procesamiento de velas. Con muchos bots, esto puede degradar el rendimiento.

### Mejoras y Optimizaciones
- **Uso de Operaciones Atómicas:** Reescribir `_update_simulation_position_db` para usar `find_one_and_update` con operadores `$inc`.
- **Manejo de Errores Seguro:** Cambiar el bloque `except` en `_check_risk_and_balance` para retornar `False` y loguear el error crítico.
- **Desacoplamiento:** Implementar un sistema de eventos (Event Bus) para notificaciones y actualizaciones de socket, eliminando dependencias circulares.
- **Caché de Bots:** Mantener un mapa en memoria de `bots_by_symbol` para evitar iteraciones innecesarias en cada tick de mercado.

---

## 2. Backtest (`api/src/application/services/backtest_service.py`)

### Descripción del Funcionamiento
El módulo de Backtest permite simular el rendimiento de estrategias en datos históricos.
- **BacktestService:** Orquesta la obtención de datos históricos, la ejecución de la estrategia paso a paso y el cálculo de métricas (PnL, Win Rate, Drawdown).
- **StrategyRunner:** Ejecuta estrategias en segundo plano para bots activos.

### Errores de Código y Lógica
1.  **Métricas Hardcodeadas:** En `BacktestService.run_backtest`, valores como `profit_factor`, `max_drawdown` y `sharpe_ratio` están hardcodeados (`1.5`, `5.0`, `1.1`), lo que da una falsa sensación de éxito.
2.  **Lógica de Simulación Simplista:** La función `_simulate_with_reversal` asume una ejecución perfecta al precio de apertura de la siguiente vela, sin considerar slippage (deslizamiento) o liquidez real, aunque sí considera spread básico.
3.  **Dependencia de `random_date`:** En `MLService` (usado por backtest indirectamente para entrenar), la obtención de datos de entrenamiento usa fechas aleatorias. Esto hace que los resultados no sean deterministas ni reproducibles.

### Mejoras y Optimizaciones
- **Cálculo Real de Métricas:** Implementar fórmulas reales para Sharpe Ratio, Sortino Ratio y Max Drawdown basadas en la serie de retornos.
- **Simulación Realista:** Incorporar un modelo de slippage y comisiones configurable en la simulación.
- **Datos Deterministas:** Permitir especificar rangos de fecha exactos para el entrenamiento y backtest para garantizar reproducibilidad.
- **Paralelismo:** Ejecutar backtests de múltiples estrategias en paralelo usando `asyncio.gather` o `ProcessPoolExecutor` para CPU-bound tasks.

---

## 3. Training / Optimización (`api/src/application/services/ai_service.py`, `ml_service.py`)

### Descripción del Funcionamiento
Este módulo se encarga de entrenar modelos de IA y optimizar el código de las estrategias.
- **AIService:** Usa LLMs para analizar código de estrategias y sugerir mejoras.
- **MLService:** Gestiona el entrenamiento de modelos de Machine Learning (ej. Random Forest, LSTM) usando datos históricos.
- **MLOptimizer:** Monitorea bots en vivo y dispara re-entrenamientos si el rendimiento cae.

### Errores de Código y Lógica
1.  **AutoML Incompleto:** En `MLOptimizer`, la lógica crítica para disparar el re-entrenamiento (`await self.ml_service.run_professional_training(...)`) está comentada o es un placeholder. El sistema detecta el bajo rendimiento pero no actúa.
2.  **Carga de Modelos Repetitiva:** En `MLService.predict`, se llama a `self.model_manager.get_model` en cada predicción. Si `ModelManager` no tiene una caché eficiente en memoria, esto causa latencia alta por I/O de disco.
3.  **Limpieza de JSON Frágil:** `AIService.optimize_strategy_code` usa expresiones regulares para extraer JSON de la respuesta del LLM. Esto es propenso a fallar si el modelo cambia el formato levemente.

### Mejoras y Optimizaciones
- **Implementar AutoML Real:** Descomentar y conectar la lógica de re-entrenamiento en `MLOptimizer`, idealmente enviando la tarea a una cola de trabajos (como Celery o BackgroundTasks de FastAPI) para no bloquear el loop principal.
- **Caché de Modelos:** Asegurar que `ModelManager` mantenga los modelos cargados en memoria (LRU Cache) para inferencia rápida.
- **Parser Robusto:** Usar librerías como `pydantic` o `instructor` para forzar y validar la salida estructurada de los LLMs, en lugar de regex manual.

---

## 4. Frontend (`web/client/src/pages/`)

### Observaciones Generales
- **Componentes Monolíticos:** Páginas como `Backtest.tsx` y `Bots.tsx` tienen más de 500-800 líneas, mezclando lógica de estado, llamadas a API, WebSockets y renderizado. Difícil de mantener y testear.
- **Lógica de Negocio en UI:** Cálculos y transformaciones de datos se hacen dentro de los componentes de React. Deberían moverse a hooks personalizados o utilidades.

### Mejoras
- **Refactorización:** Dividir las páginas grandes en componentes más pequeños (`BotList`, `BotChart`, `TradeHistory`).
- **Custom Hooks:** Extraer la lógica de conexión WebSocket y fetching de datos a hooks como `useBotData`, `useBacktestRunner`.
