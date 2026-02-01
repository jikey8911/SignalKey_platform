import sys
import os

# Add project root to path
sys.path.append(os.path.abspath("e:/antigravity/signaalKei_platform"))

def check_import(module_name):
    try:
        __import__(module_name)
        print(f"✅ Import successful: {module_name}")
    except ImportError as e:
        print(f"❌ Import failed: {module_name} - {e}")
    except SyntaxError as e:
        print(f"❌ Syntax error in {module_name}: {e}")
    except Exception as e:
        print(f"⚠️ Error importing {module_name}: {e}")

print("--- Verifying Sprint 7 & 8 Changes ---")
check_import("api.src.domain.services.risk_manager")
check_import("api.src.application.services.ml_optimizer")
check_import("api.src.adapters.driving.telegram.commander")
check_import("api.src.adapters.driven.exchange.ccxt_adapter")

print("\n--- Done ---")
