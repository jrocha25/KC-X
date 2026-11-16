"""Runtime configuration, read from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

# Repository root: holds certs/ and questions/.
BASE_DIR = Path(os.environ.get("KCX_DATA_DIR", Path(__file__).resolve().parent.parent))

# SQLite file. In Docker this is /data/kcx.db on the `kcx-data` named volume.
DB_PATH = Path(os.environ.get("KCX_DB_PATH", BASE_DIR / "kcx.db"))
