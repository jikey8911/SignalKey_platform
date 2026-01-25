from typing import List, Dict, Any
import json
from .base import BaseStrategy

class SniperStrategy(BaseStrategy):
    """
    High-Accuracy 'Sniper' Strategy.
    
    Philosophy:
    - Conservative entry: Only enter when stars align.
    - Factor Confluence: Requires at least 3 technical factors.
    - Protection First: Tight Stop Losses, reasonable Take Profits.
    - Goal: > 60% Win Rate by filtering out 'noise' signals.
    """
    
    @property
    def name(self) -> str:
        return "sniper_v1"
        
    @property
    def description(self) -> str:
        return "High accuracy (>60%) strategy focusing on confluence and risk management. Filters weak signals."

    def build_prompt(self, recent_candles: List[dict], current_price: float) -> str:
        # Construct a textual representation of the candles for context
        candles_text = ""
        for i, c in enumerate(recent_candles):
            candles_text += f"Idx {i}: T={c.get('time', c.get('timestamp'))} O={c['open']} H={c['high']} L={c['low']} C={c['close']} V={c['volume']}\n"

        prompt = f"""
ACT AS AN INSTITUTIONAL TRADING AI DEDICATED TO HIGH-ACCURACY SIGNALS (>60% WIN RATE).
Your name is 'SniperAI'. You do NOT trade noise. You only trade high-probability setups.

DATE CONTEXT:
The raw candle data (OHLCV) provided below ends with the current moment.
Current Price: {current_price}

DATA:
{candles_text}

TASK:
Analyze the market structure, trend, momentum, and volume.
You must return a JSON decision.

STRICT RULES FOR 'BUY' or 'SELL':
1. CONFLUENCE: You need at least 3 distinct technical reasons (e.g., Support bounce + Bullish Engulfing + RSI Divergence).
2. RISK/REWARD: The potential TP must be at least 1.5x the risk to SL.
3. CONFIDENCE: If you are not >80% sure, output "HOLD". BETTER TO MISS A TRADE THAN LOSE MONEY.

RESPONSE FORMAT (JSON ONLY):
{{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": <float 0-10>,
  "reasoning": "<concise explanation of the 3 confluence factors or why you chose HOLD>",
  "entry_price": {current_price},
  "tp": [
     {{ "price": <price_tp1>, "percent": <pct_dist_1> }},
     {{ "price": <price_tp2>, "percent": <pct_dist_2> }}
  ],
  "sl": <price_sl>,
  "leverage": <int_1_to_20>
}}

Output ONLY valid JSON. No markdown formatting.
"""
        return prompt
