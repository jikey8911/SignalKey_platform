from typing import List, Dict

class SniperStrategy:
    """
    Estrategia optimizada para entradas precisas (Sniper)
    """
    def build_prompt(self, window: List[dict], current_price: float) -> str:
        """
        Construye el prompt específico para la estrategia Sniper
        """
        return f"""
        Estrategia SNIPER activada. Analiza la siguiente ventana de precios (últimas 10 velas) buscando entradas de alta precisión.
        
        Precio Actual: {current_price}
        
        Datos:
        {window}
        
        Reglas SNIPER:
        - Busca divergencias RSI
        - Busca patrones de velas de reversión claros (martillo, estrella fugaz)
        - Solo opera si el riesgo/beneficio es > 1:3
        - Entradas limit preferidas
        
        Devuelve formato JSON estándar.
        """
