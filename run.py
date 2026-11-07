"""Launch directly from this source checkout without installing any packages."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kopier_commander.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
