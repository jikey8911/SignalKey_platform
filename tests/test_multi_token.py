import asyncio
import os
import sys
from unittest.mock import MagicMock

# Añadir el directorio raíz al path para importar los módulos de la API
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.services.ai_service import AIService
from api.core.domain.signal import RawSignal
from api.infrastructure.adapters.ai_adapter import AIAdapter

async def test_multi_token_parsing():
    print("=== Testing Multi-Token Signal Parsing ===")
    
    ai_service = AIService()
    
    # Simular una señal con múltiples tokens
    multi_token_text = """
    🚨 NEW OPPORTUNITIES 🚨
    
    1. $SOL looks bullish, entering at 100, TP 110, SL 95. Spot market.
    
    2. $BTC Short on Futures x20, entry 40000, TP 38000, SL 41000.
    
    3. $BONK on Solana DEX (Raydium). Buying at 0.00001, high risk!
    """
    
    print(f"Input text:\n{multi_token_text}")
    print("-" * 30)
    
    try:
        # Llamar al servicio (esto usará la IA real si hay llaves configuradas)
        # Para esta prueba, imprimiremos lo que el adaptador intentaría procesar
        adapter = AIAdapter()
        
        # Simulamos una respuesta JSON de la IA para probar el parsing sin gastar tokens si no hay llaves
        mock_response = """
        [
            {
                "decision": "BUY",
                "symbol": "SOL",
                "market_type": "SPOT",
                "is_safe": true,
                "risk_score": 2.5,
                "confidence": 0.9,
                "reasoning": "Technical breakout on SOL",
                "parameters": {
                    "entry_price": 100.0,
                    "entry_type": "market",
                    "tp": [{"price": 110.0, "percent": 100}],
                    "sl": 95.0,
                    "leverage": 1
                }
            },
            {
                "decision": "SELL",
                "symbol": "BTC",
                "market_type": "FUTURES",
                "is_safe": true,
                "risk_score": 4.0,
                "confidence": 0.85,
                "reasoning": "Overbought BTC, correction expected",
                "parameters": {
                    "entry_price": 40000.0,
                    "entry_type": "limit",
                    "tp": [{"price": 38000.0, "percent": 100}],
                    "sl": 41000.0,
                    "leverage": 20
                }
            },
            {
                "decision": "BUY",
                "symbol": "BONK",
                "market_type": "DEX",
                "is_safe": false,
                "risk_score": 8.5,
                "confidence": 0.7,
                "reasoning": "Meme coin hype on Solana",
                "parameters": {
                    "entry_price": 0.00001,
                    "entry_type": "market",
                    "tp": [{"price": 0.00002, "percent": 100}],
                    "sl": 0.000005,
                    "network": "solana"
                }
            }
        ]
        """
        
        print("Testing Parser with mock multi-token JSON response...")
        analyses = adapter._parse_response(mock_response)
        
        print(f"Parsed {len(analyses)} analysis results:")
        for i, analysis in enumerate(analyses):
            print(f"\nAnalysis {i+1}:")
            print(f"  Symbol: {analysis.symbol}")
            print(f"  Decision: {analysis.decision}")
            print(f"  Market: {analysis.market_type}")
            print(f"  Leverage: {analysis.parameters.leverage}")
            print(f"  TPs: {[t.price for t in analysis.parameters.tp]}")
            print(f"  Is Safe: {analysis.is_safe}")
        
        if len(analyses) == 3:
            print("\n✅ Multi-token parsing SUCCESSFUL!")
        else:
            print(f"\n❌ Multi-token parsing FAILED (Expected 3, got {len(analyses)})")

    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        await ai_service.close()

if __name__ == "__main__":
    asyncio.run(test_multi_token_parsing())
