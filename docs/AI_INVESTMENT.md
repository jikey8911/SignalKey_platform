# Recomendación de Inversión con IA

**Fecha:** 2026-02-20  
**Estado:** ✅ Implementado  
**Issue:** Usuarios nuevos no saben cuánto capital asignar a un bot.

---

## 🎯 Objetivo

Proporcionar una sugerencia de inversión **segura y personalizada** basada en:
1.  **Balance Disponible:** Capital real o simulado del usuario.
2.  **Perfil de Riesgo:** Low, Medium, High.
3.  **Políticas Globales:** Límites mínimos y máximos configurados en el sistema (`botWalletPolicy`).

---

## 🧠 Lógica de Cálculo

El sistema utiliza una fórmula ponderada por riesgo, ajustada por límites globales:

### 1. Factores de Riesgo
| Nivel | % del Balance | Descripción |
| :--- | :--- | :--- |
| **LOW** | **2%** | Conservador. Ideal para probar estrategias nuevas. |
| **MEDIUM** | **5%** | Equilibrado. Estándar para la mayoría de bots. |
| **HIGH** | **10%** | Agresivo. Mayor exposición, mayor potencial de ganancia/pérdida. |
| **DEGEN** | **20%** | Solo para usuarios avanzados (oculto en UI). |

### 2. Límites Globales (`botWalletPolicy`)
Estos límites actúan como "clamp" (abrazadera) para asegurar que la inversión nunca sea ridículamente baja ni peligrosamente alta.

*   **Min Allocation:** $10 USDT (default)
*   **Max Allocation:** $1000 USDT (default)
*   **Global Cap:** Nunca se recomienda más del 20% del balance total en un solo bot.

### 3. Fórmula Final
```python
raw_amount = balance * risk_factor
final_amount = clamp(raw_amount, min_alloc, max_alloc)
final_amount = min(final_amount, balance_available) # Guardrail final
```

---

## 🔌 API Endpoint

### `POST /api/ai/recommend_investment`

#### Request Body
```json
{
  "symbol": "BTC/USDT",
  "risk_level": "medium",
  "market_type": "spot"
}
```

#### Response (200 OK)
```json
{
  "symbol": "BTC/USDT",
  "recommended_amount": 150.0,
  "min_amount": 10.0,
  "max_safe_amount": 200.0,
  "balance_used_pct": 5.0,
  "risk_level": "medium",
  "reasoning": "Based on your medium risk profile and available balance ($3000.00), we recommend allocating $150.00. This represents 5.0% of your total capital, keeping you within safe limits (Min: $10.0, Max: $1000.0)."
}
```

---

## 🧪 Testing

Puedes probar la funcionalidad con el script incluido:

```bash
python scripts/test_ai_recommendation.py
```

Esto simulará peticiones con diferentes niveles de riesgo y mostrará las recomendaciones generadas.

---

## 📝 Notas de Implementación

*   Actualmente utiliza el balance **simulado** (`virtual_balances`) por seguridad.
*   En el futuro, se puede extender para leer balances **reales** de exchanges conectados (CCXT) si `market_type != 'simulated'`.
*   La lógica es **determinista** por ahora, pero está preparada para integrar modelos de lenguaje (LLMs) que generen explicaciones más ricas en el campo `reasoning`.
