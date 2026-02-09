# Plan de Implementación: Mejoras y Correcciones

## Fase 1: Corrección de Errores Críticos (Prioridad Alta)

### 1.1. Seguridad y Consistencia en Bots (`api/src/application/services/execution_engine.py`)
- **Problema:** Condición de carrera en actualizaciones de saldo simulado y "Fail-open" en validación de riesgo.
- **Acción:**
    - Modificar `_update_simulation_position_db` para usar operaciones atómicas de MongoDB (`$inc`, `$set`, `$setOnInsert`) en lugar de lectura-modificación-escritura.
    - Cambiar la lógica de manejo de excepciones en `_check_risk_and_balance`: retornar `False` (bloquear operación) en caso de error de base de datos o conexión, y registrar el evento como crítico.

### 1.2. Estabilidad del Backtest (`api/src/application/services/backtest_service.py`)
- **Problema:** Métricas hardcodeadas y simulación simplista que puede dar falsos positivos.
- **Acción:**
    - Implementar el cálculo real de `Sharpe Ratio`, `Sortino Ratio` y `Max Drawdown` basado en la serie de retornos del backtest.
    - Añadir parámetros de configuración para `slippage` y `commission` en la función `run_backtest` y aplicarlos en `_simulate_with_reversal`.

### 1.3. Robustez en Entrenamiento (`api/src/application/services/ml_optimizer.py`)
- **Problema:** Lógica de AutoML incompleta/comentada. El sistema detecta bajo rendimiento pero no re-entrena.
- **Acción:**
    - Descomentar y corregir la llamada a `self.ml_service.run_professional_training` (o función equivalente) dentro de `check_and_retrain`.
    - Asegurar que esta tarea se ejecute en segundo plano (`BackgroundTasks` de FastAPI o similar) para no bloquear el bucle principal del `StrategyRunner`.

---

## Fase 2: Optimizaciones de Rendimiento (Prioridad Media)

### 2.1. Eficiencia en SignalBotService (`api/src/application/services/bot_service.py`)
- **Problema:** Iteración ineficiente sobre todos los bots en cada actualización de vela.
- **Acción:**
    - Implementar un mapa en memoria `self._bots_by_symbol_exchange` que se actualice al iniciar/detener bots.
    - Usar este mapa en `_handle_candle_update` para obtener directamente los bots relevantes en O(1) o O(N_bots_per_symbol) en lugar de filtrar toda la lista.

### 2.2. Caché de Modelos ML (`api/src/infrastructure/ai/model_manager.py`)
- **Problema:** Carga repetitiva de modelos `.pkl` desde disco en cada predicción.
- **Acción:**
    - Verificar y reforzar la implementación de `ModelManager` para que utilice `lru_cache` o un diccionario estático para mantener los modelos cargados en memoria.
    - Implementar una política de desalojo (TTL o LRU) si la memoria es limitada.

### 2.3. Refactorización Frontend (`web/client/src/pages/`)
- **Problema:** Componentes monolíticos difíciles de mantener.
- **Acción:**
    - Extraer la lógica de conexión WebSocket de `Bots.tsx` y `Backtest.tsx` a un hook personalizado `useBotSocket` y `useBacktestSocket`.
    - Dividir `Bots.tsx` en `BotList.tsx`, `BotDetail.tsx` y `BotChart.tsx`.

---

## Fase 3: Mejoras de Calidad y Mantenibilidad (Prioridad Baja)

### 3.1. Eliminación de Dependencias Circulares
- **Problema:** Importaciones dentro de métodos en servicios.
- **Acción:**
    - Refactorizar la inyección de dependencias en `SignalBotService` y `BacktestService`.
    - Usar un patrón de Event Bus para desacoplar la notificación de sockets de la lógica de negocio.

### 3.2. Validación de Salida LLM
- **Problema:** Uso de regex frágil para parsear JSON de la IA.
- **Acción:**
    - Migrar a `pydantic` o `instructor` para definir esquemas estrictos de respuesta para la generación de código de estrategias.
