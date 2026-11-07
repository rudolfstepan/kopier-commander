"""User-specific state locations, separate from the application source."""
import os
from pathlib import Path
import sys


def data_directory() -> Path:
    if override := os.environ.get("KOPIER_COMMANDER_DATA_DIR"):
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "KopierCommander"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "KopierCommander"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "kopier-commander"
