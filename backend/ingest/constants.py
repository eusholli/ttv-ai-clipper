from pathlib import Path

# Constants
CACHE_DIR = Path("cache/")
CLIP_DIR = Path("clip/")
LOG_DIR = Path("logs/")
MAX_WORKERS = 4  # Adjust based on system capabilities
MIN_DURATION = 10  # Minimum duration for a clip in seconds

# Ensure directories exist
for directory in [CACHE_DIR, CLIP_DIR, LOG_DIR]:
    directory.mkdir(exist_ok=True)
