# Re-entrenamiento de Modelos v2.0

**Fecha:** 2026-02-20  
**Estado:** ✅ Listo para ejecutar  
**Objetivo:** Actualizar los modelos de Machine Learning para usar las nuevas features optimizadas de las estrategias v2.0.

---

## 🚀 Contexto

Las estrategias spot fueron optimizadas (v2.0) con nuevas métricas técnicas:
*   Divergencias (RSI, MACD, OBV)
*   Pendientes (Slope) de indicadores
*   Normalización de osciladores (0-1)
*   Filtros de volumen relativo

Los modelos ML antiguos no conocen estas nuevas columnas, por lo que su predicción es subóptima. Este proceso re-entrena los modelos Random Forest para aprovechar al máximo la nueva información.

---

## 📋 Instrucciones

### 1. Ejecutar Script de Entrenamiento

Este script detecta automáticamente todas las estrategias en `api/src/domain/strategies/spot/` y entrena un modelo específico para cada una.

```bash
# Desde la raíz del proyecto (signaalKei_platform)
python scripts/retrain_models.py
```

### 2. Verificar Resultados

El script generará archivos `.pkl` en:
`api/data/models/spot/`

Ejemplo de salida esperada:
*   `spot_momentum_rf.pkl`
*   `spot_rsi_strategy_rf.pkl`
*   `spot_macd_rf.pkl`
*   ... (y así para las 13 estrategias)

### 3. Configuración

El script por defecto utiliza:
*   **Símbolos:** BTC, ETH, SOL, XRP, BNB (top 5 para generalización)
*   **Timeframe:** 1h
*   **Días:** 180 (6 meses)
*   **Modelo:** RandomForestClassifier

Si deseas cambiar esto, edita `scripts/retrain_models.py` directamente.

---

## ⚠️ Nota Importante

El entrenamiento requiere datos históricos. Si no tienes datos descargados en `api/data/cache/`, el script intentará descargarlos vía CCXT (puede tardar dependiendo de tu conexión).

Asegúrate de tener conexión a internet estable.
