print("Iniciando script de depuración...")
import sys
import os

print("Añadiendo paths...")
sys.path.append(os.getcwd())

try:
    print("Intentando importar ccxt.pro...")
    import ccxt.pro as ccxt
    print("ccxt.pro importado correctamente.")
    
    print("Intentando importar MarketStreamService...")
    from api.src.adapters.driven.exchange.stream_service import MarketStreamService
    print("MarketStreamService importado correctamente.")
    
    # Intentamos instanciarlo
    print("Instanciando MarketStreamService...")
    service = MarketStreamService()
    print("MarketStreamService instanciado.")
    
except Exception as e:
    print(f"Error detectado durante importación: {e}")
except BaseException as e:
    print(f"Error base detectado (podría ser un cuelgue): {e}")

print("Script terminado.")
