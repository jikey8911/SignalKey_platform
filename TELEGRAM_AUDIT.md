# Reporte de Auditoría: Integración de Telegram

## Resumen Ejecutivo
La integración actual de Telegram funciona parcialmente pero presenta deuda técnica significativa en términos de arquitectura y mantenibilidad. Se ha detectado duplicidad de lógica de negocio en la capa de infraestructura y una violación del principio de encapsulamiento entre el adaptador y el cliente de Telegram.

## Métricas del Proyecto
- **Prioridad:** Alta 🔴
  - *Justificación:* La duplicidad de funciones de alerta y el acceso directo a propiedades internas (`client`) hacen que el sistema sea frágil ante cambios en la librería `telethon` o en la lógica de conexión.
- **Esfuerzo Estimado:** Medio (3-5 horas)
- **LOC/h (Líneas de Código/Hora):** ~50 líneas refactorizadas.

## Análisis Técnico Detallado

### 1. Duplicidad de Responsabilidades
- **Archivo:** `api/src/infrastructure/telegram/telegram_bot.py`
- **Problema:** La clase `TelegramUserBot` contiene un método `send_trade_alert` (Líneas 207-220). Esto es incorrecto arquitectónicamente; la infraestructura no debe saber sobre "trades" o "alertas", solo sobre enviar mensajes.
- **Archivo:** `api/src/adapters/driven/notifications/telegram_adapter.py`
- **Problema:** La clase `TelegramAdapter` *también* tiene `send_trade_alert`. Esta es la ubicación correcta para la lógica de negocio (formato del mensaje), pero actualmente compite con la implementación de infraestructura.

### 2. Violación de Encapsulamiento
- **Archivo:** `api/src/adapters/driven/notifications/telegram_adapter.py`
- **Código:** `await self.bot.client.send_message('me', msg, parse_mode='markdown')`
- **Problema:** El adaptador accede directamente a `self.bot.client`. Si `TelegramUserBot` cambia su implementación interna (ej. cambia de librería o renombra `client`), el adaptador fallará. `TelegramUserBot` debería exponer un método público genérico `send_message`.

### 3. Manejo de Errores y Conexión
- El adaptador verifica `if not self.bot or not self.bot.client`, pero no verifica explícitamente si el cliente está *conectado* (`is_connected()`) antes de intentar enviar, lo que puede causar excepciones no controladas en tiempo de ejecución si la conexión se cae.

## Tickets de Trabajo Generados

### TICKET-001: Refactorización de Capa de Infraestructura
- **Título:** Eliminar lógica de negocio de `TelegramUserBot`.
- **Descripción:** Remover el método `send_trade_alert` de `api/src/infrastructure/telegram/telegram_bot.py`.
- **Criterios de Aceptación:**
  - `TelegramUserBot` no debe contener referencias a "trades" o "alerts".
  - Crear un método genérico `async def send_message(self, target: str, message: str) -> bool` que maneje internamente la verificación de conexión y reintentos básicos.

### TICKET-002: Actualización de Adaptador de Notificaciones
- **Título:** Usar método público de envío en `TelegramAdapter`.
- **Descripción:** Modificar `api/src/adapters/driven/notifications/telegram_adapter.py` para usar `self.bot.send_message(...)` en lugar de acceder a `self.bot.client`.
- **Criterios de Aceptación:**
  - El código no debe importar ni depender directamente de objetos de `telethon` en el adaptador.
  - El manejo de errores debe delegarse a la respuesta del método `send_message`.

### TICKET-003: Verificación de Conexión Robusta
- **Título:** Implementar chequeo de salud de conexión antes de envío.
- **Descripción:** Asegurar que antes de cualquier envío, se verifique `is_connected()`. Si no está conectado, intentar una reconexión rápida o fallar controladamente sin lanzar excepciones crudas.

## Plan de Acción Inmediato
1. Crear script de prueba (mock) para validar la lógica actual y futura.
2. Ejecutar refactorización TICKET-001 y TICKET-002.
3. Verificar con script de prueba.

## Resultados de la Ejecución
Se han completado las tareas de refactorización y verificación.

### Acciones Realizadas:
1.  **Refactorización de `TelegramUserBot`:** Se eliminó `send_trade_alert` y se reemplazó por `send_message`, desacoplando la lógica de negocio de la infraestructura.
2.  **Actualización de `TelegramAdapter`:** Ahora utiliza `bot.send_message` en lugar de acceder directamente a `client`.
3.  **Verificación:** Se ejecutó un script de prueba (`api/tests/verify_telegram_logic.py`) que simuló escenarios de envío exitoso y fallos de conexión. Los resultados confirmaron que el manejo de errores es robusto y no provoca caídas del sistema.

### Estado Final:
-   **Arquitectura:** Mejorada (Separación de responsabilidades clara).
-   **Estabilidad:** Incrementada (Manejo de excepciones centralizado).
-   **Pruebas:** Exitosas.
