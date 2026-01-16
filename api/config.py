import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    
    # GMGN DEX
    GMGN_API_KEY = os.getenv("GMGN_API_KEY", "")
    GMGN_API_URL = os.getenv("GMGN_API_URL", "https://api.gmgn.ai")
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "")
    
    # CEX Configuration
    EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance")
    CEX_API_KEY = os.getenv("CEX_API_KEY", "")
    CEX_API_SECRET = os.getenv("CEX_API_SECRET", "")
    CEX_PASSWORD = os.getenv("CEX_PASSWORD", "")  # Passphrase
    CEX_UID = os.getenv("CEX_UID", "")  # Para OKX, KuCoin, etc
    
    # DEX Wallet
    DEX_WALLET_PRIVATE_KEY = os.getenv("DEX_WALLET_PRIVATE_KEY", "")
    
    # Demo Mode
    DEMO_MODE = os.getenv("DEMO_MODE", "True").lower() == "true"
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trading_bot.db")
    
    # API Server
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
