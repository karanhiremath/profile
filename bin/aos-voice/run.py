"""Run the same packaged entry point from a source checkout without installing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from aos_voice.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
