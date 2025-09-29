"""Application-wide configuration values."""

from pathlib import Path

TICK_SECONDS = 0.5
PREFS_PATH = Path.home() / ".four3_prefs.json"
DEFAULT_INPUTS = ("40.00", "50.00", "99.99")

RAMP_DURATION_MIN = 25.0
DISPLAY_Y_MAX_CM = 10.0

