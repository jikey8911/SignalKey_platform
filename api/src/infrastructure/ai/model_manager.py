import os
import joblib
import logging
from typing import Dict, Any, Optional
from threading import Lock

logger = logging.getLogger(__name__)

class ModelManager:
    _instance = None
    _lock = Lock()
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ModelManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.models: Dict[str, Any] = {} # Key: "market_type/strategy_name"
        self.models_dir = "api/data/models"
        self._initialized = True
        logger.info("ModelManager initialized (Singleton)")

    def load_all_models(self, models_dir: str = None):
        """Recursively loads all .pkl models from the directory into memory."""
        target_dir = models_dir or self.models_dir
        if not os.path.exists(target_dir):
            logger.warning(f"Models directory not found: {target_dir}")
            return

        logger.info(f"Loading models from {target_dir}...")
        
        count = 0
        # Walk through directory to find models (supporting subdirs like 'spot', 'futures')
        for root, _, files in os.walk(target_dir):
            for file in files:
                if file.endswith(".pkl"):
                    full_path = os.path.join(root, file)
                    try:
                        # Construct key: e.g., "spot/rsi_strategy" or just "rsi_strategy"
                        rel_path = os.path.relpath(full_path, target_dir)
                        # Normalize key to forward slashes and remove extension
                        key = rel_path.replace("\\", "/").replace(".pkl", "")
                        
                        model = joblib.load(full_path)
                        self.models[key] = model
                        count += 1
                        logger.debug(f"Loaded model: {key}")
                    except Exception as e:
                        logger.error(f"Failed to load model {file}: {e}")
        
        logger.info(f"ModelManager: {count} models loaded into RAM.")

    def get_model(self, strategy_name: str, market_type: str = "spot") -> Optional[Any]:
        """
        Retrieves a loaded model. 
        Tries specific path first (market_type/strategy), then root (strategy).
        """
        # 1. Try specific: "spot/RSI_Strategy"
        key_specific = f"{market_type.lower()}/{strategy_name}"
        if key_specific in self.models:
            return self.models[key_specific]
            
        # 2. Try root/generic: "RSI_Strategy"
        if strategy_name in self.models:
            return self.models[strategy_name]
            
        return None

    def reload_model(self, strategy_name: str, market_type: str = "spot") -> bool:
        """Reloads a specific model from disk without restarting."""
        # Check specific path
        path_specific = os.path.join(self.models_dir, market_type.lower(), f"{strategy_name}.pkl")
        path_root = os.path.join(self.models_dir, f"{strategy_name}.pkl")
        
        target_path = None
        key = None
        
        if os.path.exists(path_specific):
            target_path = path_specific
            key = f"{market_type.lower()}/{strategy_name}"
        elif os.path.exists(path_root):
            target_path = path_root
            key = strategy_name
            
        if target_path:
            try:
                model = joblib.load(target_path)
                self.models[key] = model
                logger.info(f"Model reloaded: {key}")
                return True
            except Exception as e:
                logger.error(f"Failed to reload model {key}: {e}")
                return False
        
        logger.warning(f"Model file not found for reload: {strategy_name}")
        return False
