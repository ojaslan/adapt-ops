"""
Configuration management for ADAPT-OPS
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / ".data"
DATA_DIR.mkdir(exist_ok=True)

# MAB Configuration
MAB_STATE_FILE = DATA_DIR / "mab_state.json"
MAB_ALPHA = float(os.getenv("MAB_ALPHA", "1.0"))
MAB_CONTEXT_DIM = int(os.getenv("MAB_CONTEXT_DIM", "16"))

# Anomaly Detection
ANOMALY_WINDOW_SIZE = int(os.getenv("ANOMALY_WINDOW_SIZE", "30"))
ANOMALY_MIN_SCORE = float(os.getenv("ANOMALY_MIN_SCORE", "0.45"))

# Healing Configuration
HEALING_COOLDOWN_SECS = float(os.getenv("HEALING_COOLDOWN_SECS", "60.0"))
HEALING_MIN_SEVERITY = int(os.getenv("HEALING_MIN_SEVERITY", "2"))

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_RELOAD = os.getenv("API_RELOAD", "false").lower() == "true"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = DATA_DIR / "adapt-ops.log"

# Feature flags
ENABLE_MAB_PERSISTENCE = os.getenv("ENABLE_MAB_PERSISTENCE", "true").lower() == "true"
ENABLE_METRICS_HISTORY = os.getenv("ENABLE_METRICS_HISTORY", "true").lower() == "true"
MAX_HISTORY_SIZE = int(os.getenv("MAX_HISTORY_SIZE", "10000"))

# GitHub Actions Integration (optional)
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", None)
GITHUB_API_TOKEN = os.getenv("GITHUB_API_TOKEN", None)

print(f"Config loaded | MAB Alpha={MAB_ALPHA} | Cooldown={HEALING_COOLDOWN_SECS}s | Data Dir={DATA_DIR}")
