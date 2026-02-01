import os
import shutil
import re

BASE_DIR = "api"
SRC_DIR = os.path.join(BASE_DIR, "src")

# Define structure
DIRS = [
    # Domain
    "src/domain/models",
    "src/domain/ports/input",
    "src/domain/ports/output",
    # Application
    "src/application/services",
    # Adapters Driving
    "src/adapters/driving/api/routers",
    # Adapters Driven
    "src/adapters/driven/persistence",
    "src/adapters/driven/exchange",
    "src/adapters/driven/ml_engine",
    "src/adapters/driven/notifications",
    # Infrastructure
    "src/infrastructure/config",
    "src/infrastructure/logging",
]

# File Mappings (Source -> Destination relative to api/)
MOVES = {
    # Models
    "models/schemas.py": "src/domain/models/schemas.py",
    # Persistence
    "models/mongodb.py": "src/adapters/driven/persistence/mongodb.py",
    "models/database.py": "src/adapters/driven/persistence/database.py",
    # Services (Application)
    "services/backtest_service.py": "src/application/services/backtest_service.py",
    "services/ml_service.py": "src/application/services/ml_service.py",
    "services/signal_bot_service.py": "src/application/services/bot_service.py",
    "services/tracker_service.py": "src/application/services/tracker_service.py",
    "services/monitor_service.py": "src/application/services/monitor_service.py",
    "services/cex_service.py": "src/application/services/cex_service.py",
    "services/dex_service.py": "src/application/services/dex_service.py",
    "services/ai_service.py": "src/application/services/ai_service.py",
    # Driven Adapters
    "services/ccxt_service.py": "src/adapters/driven/exchange/ccxt_adapter.py",
    "services/socket_service.py": "src/adapters/driven/notifications/socket_service.py",
    # Routers (Driving)
    "routers/backtest_router.py": "src/adapters/driving/api/routers/backtest_router.py",
    "routers/ml_router.py": "src/adapters/driving/api/routers/ml_router.py",
    "routers/telegram_router.py": "src/adapters/driving/api/routers/telegram_router.py",
    "routers/market_data_router.py": "src/adapters/driving/api/routers/market_data_router.py",
    "routers/websocket_router.py": "src/adapters/driving/api/routers/websocket_router.py",
}

# Import Replacements
IMPORT_MAP = {
    "api.models.schemas": "api.src.domain.models.schemas",
    "api.models.mongodb": "api.src.adapters.driven.persistence.mongodb",
    "api.models.db": "api.src.adapters.driven.persistence.mongodb", # db is in mongodb.py
    "api.services.backtest_service": "api.src.application.services.backtest_service",
    "api.services.ml_service": "api.src.application.services.ml_service",
    "api.services.ccxt_service": "api.src.adapters.driven.exchange.ccxt_adapter",
    "api.services.signal_bot_service": "api.src.application.services.bot_service",
    # Add more as needed
}

def create_structure():
    print("Creating directory structure...")
    for d in DIRS:
        path = os.path.join(BASE_DIR, d)
        os.makedirs(path, exist_ok=True)
        # Add __init__.py
        with open(os.path.join(path, "__init__.py"), 'w') as f:
            pass

def move_files():
    print("Moving files...")
    for src, dst in MOVES.items():
        src_path = os.path.join(BASE_DIR, src)
        dst_path = os.path.join(BASE_DIR, dst)
        
        if os.path.exists(src_path):
            print(f"Moving {src} -> {dst}")
            shutil.move(src_path, dst_path)
        else:
            print(f"Warning: Source {src} not found")

def update_imports():
    print("Updating imports...")
    # Walk through all python files in api/
    for root, dirs, files in os.walk(BASE_DIR):
        # Exclude venv and pycache
        if 'venv' in dirs:
            dirs.remove('venv')
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')
            
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                new_content = content
                
                # Replace imports
                # 1. Direct replacements from map
                for old, new in IMPORT_MAP.items():
                    new_content = new_content.replace(old, new)
                
                # 2. General patterns
                # "from api.services.ccxt_service import" -> "from api.src.adapters.driven.exchange.ccxt_adapter import"
                # Doing this dynamically based on MOVES might be risky but let's try strict strings first
                
                # Custom fixes
                new_content = new_content.replace("from api.routers", "from api.src.adapters.driving.api.routers")
                
                if new_content != content:
                    print(f"Updating imports in {path}")
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)

def main():
    create_structure()
    move_files()
    update_imports()
    print("Refactor complete.")

if __name__ == "__main__":
    main()
