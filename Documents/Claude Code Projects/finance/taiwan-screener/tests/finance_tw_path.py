"""Inserts the taiwan-screener package root onto sys.path for pytest."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ensure_path() -> None:
    """Explicit callable for `from finance_tw_path import ensure_path`."""
    return None
