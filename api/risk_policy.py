"""Re-export of src.risk_policy for API runtime."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT), str(_ROOT / "src")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.risk_policy import *  # noqa: F401, F403
