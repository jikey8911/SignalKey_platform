import os
from dotenv import load_dotenv

from pathlib import Path
from pymongo.uri_parser import parse_uri

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

def get_default_db_name(uri):
    try:
        parsed = parse_uri(uri)
        return parsed.get("database") or "signalkey_platform"
    except:
        return "signalkey_platform"

class Config:
    # API Keys
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
    TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
    GMGN_API_KEY = os.getenv("GMGN_API_KEY")
    XAI_API_KEY = os.getenv("XAI_API_KEY")
    ZERO_EX_API_KEY = os.getenv("ZERO_EX_API_KEY")
    ZERO_EX_BASE_URL = os.getenv("ZERO_EX_BASE_URL", "https://api.0x.org")
    PORT = int(os.getenv("PORT", 8000))
    API_BASE_URL = os.getenv("API_BASE_URL", f"http://localhost:{PORT}")
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", get_default_db_name(MONGODB_URI))
    # CEX Config (Example for CCXT)
    EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance")
    CEX_API_KEY = os.getenv("CEX_API_KEY")
    CEX_SECRET = os.getenv("CEX_SECRET")
    CEX_PASSWORD = os.getenv("CEX_PASSWORD") # También conocido como Passphrase
    CEX_UID = os.getenv("CEX_UID")
    
    # DEX Config
    DEX_WALLET_PRIVATE_KEY = os.getenv("DEX_WALLET_PRIVATE_KEY")
    SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    
    # Security
    JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
    
    # App Settings
    DEBUG = os.getenv("DEBUG", "True") == "True"
    DEMO_MODE = os.getenv("DEMO_MODE", "True") == "True"
    PORT = int(os.getenv("PORT", 8000))
