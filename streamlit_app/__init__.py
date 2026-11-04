"""Streamlit application package."""
import sys
from pathlib import Path

# Ensure repo root is always in sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
