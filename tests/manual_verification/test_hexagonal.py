import asyncio
import sys
import os

# Añadir el directorio actual al path para importar api
sys.path.append(os.getcwd())

from api.services.ai_service import AIService
from api.models.schemas import AnalysisResult

async def test_ai_analysis():
    service = AIService()
    
    # Simular una señal de Telegram
    signal_text = "BUY BTC/USDT entry 95000 tp 100000, 105000 sl 90000"
    
    print(f"Analizando señal: {signal_text}")
    
    # Usar config vacía para que use variables de entorno (o falle graciosamente)
    config = {"aiProvider": "gemini"} 
    
    try:
        result = await service.analyze_signal(signal_text, config)
        print("\nResultado del Análisis:")
        print(f"Decisión: {result.decision}")
        print(f"Símbolo: {result.symbol}")
        print(f"Market Type: {result.market_type}")
        print(f"Precio Entrada: {result.parameters.get('entry_price')}")
        print(f"Take Profits: {result.parameters.get('tp')}")
        print(f"Stop Loss: {result.parameters.get('sl')}")
        print(f"Razonamiento: {result.reasoning}")
    except Exception as e:
        print(f"Error durante la prueba: {e}")

if __name__ == "__main__":
    asyncio.run(test_ai_analysis())
