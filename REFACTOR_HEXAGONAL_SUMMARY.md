# Resumen de Refactorización: Arquitectura Hexagonal y DDD

Se ha realizado una refactorización profunda del núcleo de procesamiento de señales en el repositorio `SignalKey_platform`, migrando de una estructura monolítica/orientada a servicios a una **Arquitectura Hexagonal (Ports & Adapters)** con principios de **Domain-Driven Design (DDD)**.

## 1. Nueva Estructura de Capas

La lógica se ha organizado en `api/src/` siguiendo tres niveles de aislamiento:

### CAPA DE DOMINIO (`api/src/domain`)
- **Entidades:** Definición de `Signal`, `SignalAnalysis`, `MarketType`, etc., como objetos puros de Python (POPOs).
- **Ports (Interfaces):** Contratos abstractos que definen qué necesita el negocio.
  - `ISignalRepository`: Para persistencia.
  - `IAIPort`: Para análisis de inteligencia artificial.
  - `INotificationPort`: Para comunicación en tiempo real.
- **Excepciones:** Definición de errores de dominio y de infraestructura genéricos.

### CAPA DE APLICACIÓN (`api/src/application`)
- **Casos de Uso:** Implementación de `ProcessSignalUseCase`. Esta clase orquesta el flujo de negocio inyectando los puertos necesarios. Es agnóstica a si los datos vienen de MongoDB, PostgreSQL o si las notificaciones van por WebSockets o Telegram.

### CAPA DE INFRAESTRUCTURA (`api/src/infrastructure`)
- **Adapters:** Implementaciones concretas de los puertos.
  - `MongoDBSignalRepository`: Adaptador para MongoDB usando Motor.
  - `AIAdapter`: Adaptador que envuelve el servicio de IA existente.
  - `SocketNotificationAdapter`: Adaptador para notificaciones vía WebSockets.
- **Inyección de Dependencias (DI):** Se ha implementado un `Container` que centraliza la creación y configuración de los adaptadores, facilitando el intercambio de tecnologías mediante variables de entorno.

## 2. Cambios Principales

1. **Desacoplamiento de `main.py`**: La función `process_signal_task` ahora es un simple punto de entrada que delega toda la responsabilidad al caso de uso correspondiente.
2. **Estandarización de Respuestas**: Los adaptadores transforman los modelos de base de datos y respuestas de APIs externas a entidades de dominio.
3. **Manejo de Errores Robusto**: Se capturan fallos de infraestructura y se envuelven en excepciones de dominio, permitiendo que la aplicación responda de forma coherente ante fallos externos.
4. **Independencia Tecnológica**: El Core no importa librerías como `motor`, `requests` o `fastapi`.

## 3. Rama de Entrega
Los cambios han sido subidos a la nueva rama: **`manuhex`**.
