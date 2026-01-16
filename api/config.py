import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Keys
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
    TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
    GMGN_API_KEY = os.getenv("GMGN_API_KEY")
    
    # CEX Config (Example for CCXT)
    EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance")
    CEX_API_KEY = os.getenv("CEX_API_KEY")
    CEX_SECRET = os.getenv("CEX_SECRET")
    CEX_PASSWORD = os.getenv("CEX_PASSWORD") # También conocido como Passphrase
    CEX_UID = os.getenv("CEX_UID")
    
    # DEX Config
    DEX_WALLET_PRIVATE_KEY = os.getenv("DEX_WALLET_PRIVATE_KEY")
    SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    
    # App Settings
    DEBUG = os.getenv("DEBUG", "True") == "True"
    DEMO_MODE = os.getenv("DEMO_MODE", "True") == "True"
    PORT = int(os.getenv("PORT", 8000))
