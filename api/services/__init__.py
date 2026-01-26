import sys
from src.application.services import *

# Explicitly alias common services if star import misses them or for explicit clarity
from src.application.services.ml_service import MLService
from src.application.services.backtest_service import BacktestService
from src.application.services.cex_service import CEXService
from src.application.services.dex_service import DEXService
from src.application.services.ai_service import AIService
from src.application.services.bot_service import SignalBotService
from src.application.services.monitor_service import MonitorService
from src.application.services.tracker_service import TrackerService
