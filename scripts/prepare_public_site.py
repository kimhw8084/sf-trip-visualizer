#!/usr/bin/env python3
"""Build the minimal static runtime published by GitHub Pages."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (ROOT / (sys.argv[1] if len(sys.argv) > 1 else ".public-site")).resolve()

FILES = (
    "index.html",
    "src/app_phase7.css",
    "src/app_phase7.js",
    "src/map_first.css",
    "vendor/maplibre-gl.css",
    "vendor/maplibre-gl.js",
    "vendor/trip-vector.js",
    "assets/vector/sf_trip.pmtiles",
    "assets/vector/yosemite_hillshade_shadow.webp",
)
DIRECTORIES = (
    "assets/vector/fonts",
    "assets/vector/sprites",
    "assets/photos/thumb",
    "assets/photos/medium",
)


def main() -> None:
    if OUTPUT == ROOT or ROOT in OUTPUT.parents and OUTPUT.name in {"src", "vendor", "assets"}:
        raise SystemExit(f"Refusing unsafe output directory: {OUTPUT}")

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    for relative in FILES:
        source = ROOT / relative
        if not source.is_file():
            raise SystemExit(f"Missing required runtime file: {relative}")
        destination = OUTPUT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    for relative in DIRECTORIES:
        source = ROOT / relative
        if not source.is_dir():
            raise SystemExit(f"Missing required runtime directory: {relative}")
        shutil.copytree(source, OUTPUT / relative)

    (OUTPUT / ".nojekyll").touch()
    files = [path for path in OUTPUT.rglob("*") if path.is_file()]
    total_bytes = sum(path.stat().st_size for path in files)
    print({"output": str(OUTPUT), "files": len(files), "bytes": total_bytes})


if __name__ == "__main__":
    main()
