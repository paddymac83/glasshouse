"""Where the API finds ingestion's SQLite store.

A plain function (not a class) so it's trivially overridable in tests
via FastAPI's `app.dependency_overrides` -- point it at a seeded temp
DB instead of hitting whatever's on disk.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DB_PATH = "../ingestion/glasshouse.db"


def get_ingestion_db_path() -> Path:
    return Path(os.environ.get("GLASSHOUSE_INGESTION_DB", DEFAULT_DB_PATH))
