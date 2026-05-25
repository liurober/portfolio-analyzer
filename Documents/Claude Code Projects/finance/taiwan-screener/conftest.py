"""Root conftest.py — makes finance_tw_path importable from all test modules."""
import sys
from pathlib import Path

# Add tests/ dir so `import finance_tw_path` works
TESTS_DIR = Path(__file__).resolve().parent / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
