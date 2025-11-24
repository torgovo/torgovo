import os
import django
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

try:
    from apps.exchanges.handlers.base import trading_manager
    print("TradingManager imported successfully")
    from apps.exchanges.handlers.bybitbot import BybitBots
    print("BybitBots imported successfully")
except Exception as e:
    print(f"Error importing bots: {e}")
    import traceback
    traceback.print_exc()
