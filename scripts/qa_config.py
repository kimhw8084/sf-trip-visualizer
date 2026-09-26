"""Shared paths for the maintained map-first browser suites."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
from trip_package import DEFAULT_PACKAGE, load_package

ACTIVE_PACKAGE = load_package(DEFAULT_PACKAGE)
MODULAR_URL = os.environ.get("TRIP_QA_URL", "http://127.0.0.1:8766/index.html")
STANDALONE_PATH = Path(
    os.environ.get(
        "TRIP_STANDALONE_PATH",
        str(ROOT / ".build" / "standalone" / f"{ACTIVE_PACKAGE['slug']}-standalone.html"),
    )
)
