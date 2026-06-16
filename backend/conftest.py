"""Pytest fixtures + path setup shared across the test suite."""

import os
import sys
from pathlib import Path

# Ensure the backend root is importable regardless of where pytest is invoked
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Tests must never hit a real DB / Redis / external API. Force-strip the env
# so an accidentally-set key doesn't make a test live-fire.
for var in ("ANTHROPIC_API_KEY", "FRED_API_KEY", "MARKETDATA_API_KEY",
             "TRADIER_API_KEY", "FMP_API_KEY", "ALPHA_VANTAGE_API_KEY",
             "DISCORD_WEBHOOK_URL", "NEWS_API_KEY"):
    os.environ.pop(var, None)
