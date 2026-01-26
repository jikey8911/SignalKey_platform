import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

print("Attempting to import IAIPort...")
try:
    from api.src.domain.ports.output.ai_port import IAIPort
    print("Success: IAIPort imported.")
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")

print("Attempting to import AIAdapter...")
try:
    from api.src.infrastructure.adapters.ai.ai_adapter import AIAdapter
    print("Success: AIAdapter imported.")
except Exception as e:
    print(f"Error importing Adapter: {e}")
