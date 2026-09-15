"""Add official-site photographs that Commons search does not cover well."""
from __future__ import annotations

import json
from pathlib import Path

import requests

from discover_photos import OUT, download_preview, sheet


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "QA" / "photo_candidates" / "candidates.json"
SOURCE_PAGE = "https://presidio.gov/explore/attractions/presidio-tunnel-tops"
ITEMS = [
    {
        "title": "Official: Presidio Tunnel Tops Golden Gate view",
        "page_url": SOURCE_PAGE,
        "source_url": "https://wp.presidio.gov/wp-content/uploads/2023/07/tunneltops2410b-1976.jpg",
        "preview_url": "https://wp.presidio.gov/wp-content/uploads/2023/07/tunneltops2410b-1976.jpg",
        "description": "Presidio Tunnel Tops with Golden Gate Bridge views",
        "categories": "Presidio Tunnel Tops",
        "artist": "The Presidio",
        "license": "Official site photograph",
    },
    {
        "title": "Official: Presidio Tunnel Tops family lawn",
        "page_url": SOURCE_PAGE,
        "source_url": "https://wp.presidio.gov/wp-content/uploads/2023/07/presidio_waw_DE6A3550-2-1.jpg",
        "preview_url": "https://wp.presidio.gov/wp-content/uploads/2023/07/presidio_waw_DE6A3550-2-1.jpg",
        "description": "Families picnicking on a Presidio Tunnel Tops lawn",
        "categories": "Presidio Tunnel Tops",
        "artist": "Rachel Styer / The Presidio",
        "license": "Official site photograph",
    },
    {
        "title": "Official: Presidio Tunnel Tops Outpost playground",
        "page_url": SOURCE_PAGE,
        "source_url": "https://wp.presidio.gov/wp-content/uploads/2023/07/20220807_TT_1stSun_Aug-_OM10222-3-1.jpg",
        "preview_url": "https://wp.presidio.gov/wp-content/uploads/2023/07/20220807_TT_1stSun_Aug-_OM10222-3-1.jpg",
        "description": "Children at the Outpost nature playground",
        "categories": "Presidio Tunnel Tops; Outpost playground",
        "artist": "The Presidio",
        "license": "Official site photograph",
    },
    {
        "title": "Official: Presidio Tunnel Tops Outpost Meadow",
        "page_url": SOURCE_PAGE,
        "source_url": "https://wp.presidio.gov/wp-content/uploads/2023/07/20250830_outpost_meadow.01.jpg",
        "preview_url": "https://wp.presidio.gov/wp-content/uploads/2023/07/20250830_outpost_meadow.01.jpg",
        "description": "Outpost Meadow picnic area at Presidio Tunnel Tops",
        "categories": "Presidio Tunnel Tops; Outpost Meadow",
        "artist": "The Presidio",
        "license": "Official site photograph",
    },
]


def main() -> None:
    candidates = json.loads(CANDIDATES.read_text())
    existing = candidates.setdefault("tunnel_tops", [])
    seen = {item["source_url"] for item in existing}
    session = requests.Session()
    session.headers.update({"User-Agent": "SFTripPersonalPhotoAcquisition/1.0 (local personal trip map; contact: codex@openai.com)"})
    for item in ITEMS:
        if item["source_url"] in seen:
            continue
        response = session.get(item["source_url"], timeout=45)
        response.raise_for_status()
        from PIL import Image
        from io import BytesIO

        with Image.open(BytesIO(response.content)) as image:
            item["width"], item["height"] = image.size
        existing.append(item)
    place_dir = OUT / "previews" / "tunnel_tops"
    place_dir.mkdir(exist_ok=True)
    for index, item in enumerate(existing):
        target = place_dir / f"{index:02d}.jpg"
        item["preview_local"] = str(target.relative_to(ROOT)) if download_preview(session, item["preview_url"], target) else None
    sheet("tunnel_tops", existing)
    CANDIDATES.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n")
    print(f"tunnel_tops {len(existing)} candidates")


if __name__ == "__main__":
    main()
