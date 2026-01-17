# Refactorización a Arquitectura Hexagonal (Rama manudev)

Este documento resume los cambios realizados en el proyecto `SignalKey_platform` para migrar el servicio de análisis de señales a una **Arquitectura Hexagonal** (también conocida como Puertos y Adaptadores).

## Objetivo de la Refactorización

El objetivo principal fue desacoplar la lógica de negocio central (Core) de los detalles de implementación externos (como las APIs de IA y los modelos de datos de FastAPI/Pydantic), facilitando la mantenibilidad, la testabilidad y la futura adición de nuevos proveedores de IA o bases de datos.

Se puso especial énfasis en el servicio `ai_service` para asegurar que la información crítica de la señal (precio de entrada, Take Profits y Stop Loss) se maneje de forma robusta y tipada.

## Nueva Estructura de Directorios

La estructura del directorio `api/` ha sido reorganizada para reflejar la arquitectura hexagonal:

| Directorio | Capa Hexagonal | Descripción |
| :--- | :--- | :--- |
| `api/core/domain` | **Dominio** | Contiene las entidades de negocio puras (`SignalAnalysis`, `RawSignal`, `TradingParameters`, etc.) y las reglas de negocio. **Independiente de cualquier framework o base de datos.** |
| `api/core/ports` | **Puertos** | Interfaces (clases abstractas) que definen cómo el Dominio interactúa con el mundo exterior (Adaptadores). Ejemplo: `AIPort`. |
| `api/core/use_cases` | **Casos de Uso** | Lógica de aplicación que orquesta las entidades del Dominio y utiliza los Puertos. Ejemplo: `ProcessSignalUseCase`. |
| `api/infrastructure/adapters` | **Adaptadores** | Implementaciones concretas de los Puertos. Conectan el Dominio con tecnologías externas. Ejemplo: `AIAdapter` (implementa `AIPort`). |
| `api/infrastructure/persistence` | **Adaptadores** | Contendrá la lógica de acceso a la base de datos (MongoDB, etc.). |
| `api/infrastructure/external_services` | **Adaptadores** | Contendrá otros servicios externos (CEX, DEX, Socket, etc.). |
| `api/application/dtos` | **DTOs** | Contendrá Data Transfer Objects si fueran necesarios para la comunicación con la capa de presentación (FastAPI). |

## Cambios Clave en el Servicio de IA

### 1. Definición de Dominio Tipada

Se crearon clases de dominio (`dataclasses`) en `api/core/domain/signal.py` para representar la señal y sus parámetros de trading de forma nativa en Python, sin depender de Pydantic.

**Estructura de Parámetros de Trading (Mejorada):**

```python
@dataclass
class TakeProfit:
    price: float
    percent: float

@dataclass
class TradingParameters:
    entry_price: Optional[float] = None
    entry_type: str = "market"
    tp: List[TakeProfit] = field(default_factory=list)
    sl: Optional[float] = None
    # ... otros campos
```

### 2. Adaptador de IA (`AIAdapter`)

El antiguo `ai_service.py` fue movido y refactorizado a `api/infrastructure/adapters/ai_adapter.py`.

*   **Implementación del Puerto:** `AIAdapter` implementa la interfaz `AIPort`, asegurando que el Dominio solo sepa de la interfaz.
*   **Lógica de Conexión:** Toda la lógica de conexión a Gemini, OpenAI, Perplexity, etc., y el manejo de claves API se encapsula aquí.
*   **Prompt Mejorado:** El prompt enviado a la IA se mantiene con la estructura JSON solicitada, garantizando que los campos `entry_price`, `tp` (lista de objetos con `price` y `percent`), y `sl` sean devueltos correctamente por el modelo de lenguaje.
*   **Mapeo de Tipos:** El adaptador es responsable de mapear la respuesta JSON de la IA a las clases de Dominio (`SignalAnalysis`, `TradingParameters`).

### 3. Fachada de Servicio (`ai_service.py`)

El archivo original `api/services/ai_service.py` ahora actúa como una **fachada**. Su única responsabilidad es:

1.  Recibir la llamada de la capa de aplicación (FastAPI/`main.py`).
2.  Mapear los datos de entrada al objeto de Dominio (`RawSignal`).
3.  Delegar la tarea al `AIAdapter`.
4.  Mapear el objeto de Dominio (`SignalAnalysis`) de vuelta al esquema de Pydantic (`AnalysisResult`) que el resto de la aplicación espera, manteniendo la compatibilidad con el código existente en `main.py`.

## Conclusión

La refactorización ha introducido una capa de abstracción que aísla la lógica de negocio de la implementación de la IA. Esto asegura que la lógica de aprobación de señales y la extracción de parámetros críticos (`entry_price`, `tp`, `sl`) sea más robusta y fácil de modificar o extender en el futuro.

Para completar la migración, se recomienda:

1.  Actualizar `main.py` y otros servicios para usar los Casos de Uso (`ProcessSignalUseCase`) en lugar de llamar directamente a los servicios.
2.  Refactorizar `schemas.py` para que use las clases de Dominio como base, o al menos para que refleje la nueva estructura de `TradingParameters`.
3.  Eliminar el antiguo `ai_service.py` y renombrar el nuevo si se desea una limpieza completa.

---
*Documento generado por Manus AI.*
