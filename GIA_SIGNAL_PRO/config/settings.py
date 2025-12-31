
import os
import sys
from pathlib import Path

# 🦁 GIA SIGNAL PRO - SETTINGS LOADER
# ----------------------------------

# Add project root to path for backend utilities
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Attempt to load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    # Priority to GIA_SIGNAL_PRO/.env then root .env
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# --- Configuration Constants ---

# 📡 Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_USERNAME = os.getenv("TELEGRAM_CHANNEL_USERNAME")

# 🌍 Localization & Meta
ASSET = os.getenv("ASSET", "XAUUSD")
TIMEFRAME = os.getenv("TIMEFRAME", "M1")
TIMEZONE = os.getenv("TIMEZONE", "UTC")

# 📂 Paths
DATA_DIR = os.getenv("DATA_DIR", r"C:\GIA_DATA")
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "GIA_SIGNAL_PRO.pkl"

# 🧠 Logic
MIN_CONFIDENCE = 20 # FORCED NUCLEAR HYPER-SCALPING MODE
ATR_THRESHOLD = float(os.getenv("ATR_THRESHOLD", 1.5))
SIGNAL_HORIZON = int(os.getenv("SIGNAL_HORIZON", 15))

# Ensure folders exist
os.makedirs(MODELS_DIR, exist_ok=True)
