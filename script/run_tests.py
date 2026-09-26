"""One-click test runner: `python script/run_tests.py` (same as running `pytest` at the repo root)."""
from __future__ import annotations

from pathlib import Path
import os
import sys

import pytest

if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    os.chdir(Path(__file__).resolve().parents[1])
    sys.exit(pytest.main(sys.argv[1:]))
