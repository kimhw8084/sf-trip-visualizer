"""Shared paths for the maintained map-first browser suites."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULAR_URL = os.environ.get("TRIP_QA_URL", "http://127.0.0.1:8766/index.html")
STANDALONE_PATH = Path(
    os.environ.get(
        "TRIP_STANDALONE_PATH",
        str(ROOT / ".build" / "standalone" / "SF_Smart_Minority_Map_First_Standalone.html"),
    )
)
