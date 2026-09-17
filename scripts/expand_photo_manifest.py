"""Add gap-audit photo slots without changing the original 84 reviewed assets."""
from __future__ import annotations

raise SystemExit("DEPRECATED LEGACY ENTRY POINT: 84-photo expansion path; use the canonical 108-photo manifest")

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests" / "asset_manifest.json"
PLACES = {
    "pier39": {
        "name": "PIER 39 Sea Lions at K-Dock",
        "sources": [
            "https://www.pier39.com/sealions/",
            "https://commons.wikimedia.org/wiki/Category:Sea_lions_at_Pier_39",
        ],
    },
    "tunnel_tops": {
        "name": "Presidio Tunnel Tops + Outpost",
        "sources": [
            "https://presidio.gov/explore/attractions/presidio-tunnel-tops",
            "https://presidio.gov/explore/attractions/outpost-playground",
        ],
    },
    "bixby": {
        "name": "Bixby Creek Bridge",
        "sources": [
            "https://dot.ca.gov/caltrans-near-me/district-5/d5-news/d5-news-9-2-2026",
            "https://commons.wikimedia.org/wiki/Category:Bixby_Creek_Bridge",
        ],
    },
    "ghirardelli": {
        "name": "Ghirardelli Square + Aquatic Park",
        "sources": [
            "https://www.ghirardellisq.com/history",
            "https://commons.wikimedia.org/wiki/Category:Ghirardelli_Square",
        ],
    },
    "cable_car": {
        "name": "Powell–Hyde Cable Car",
        "sources": [
            "https://www.sfmta.com/routes/powell-hyde-cable-car",
            "https://www.sfmta.com/getting-around/muni/traveling-young-children",
        ],
    },
    "carmel": {
        "name": "Carmel-by-the-Sea + Carmel Beach",
        "sources": [
            "https://www.carmelcalifornia.com/visit-carmel/",
            "https://www.carmelcalifornia.com/carmel-beach/",
        ],
    },
    "el_capitan": {
        "name": "El Capitan Meadow",
        "sources": [
            "https://www.nps.gov/places/000/el-capitan-meadow.htm",
            "https://commons.wikimedia.org/wiki/Category:El_Capitan_(Yosemite)",
        ],
    },
    "monterey_wharf": {
        "name": "Old Fisherman’s Wharf, Monterey",
        "sources": [
            "https://www.seemonterey.com/regions/monterey/old-fishermans-wharf/",
            "https://commons.wikimedia.org/wiki/Category:Fisherman%27s_Wharf_(Monterey,_California)",
        ],
    },
}
ROLES = {
    "HERO": ("hero", "instantly identifies the place"),
    "EXPERIENCE": ("experience", "shows what the family will do or see"),
    "SCALE_CONTEXT": ("scale_context", "shows spatial scale and surrounding context"),
}


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    existing = {(asset["place_key"], asset["role"]) for asset in manifest["assets"]}
    for place_key, place in PLACES.items():
        for role, (suffix, goal) in ROLES.items():
            if (place_key, role) in existing:
                continue
            manifest["assets"].append({
                "place_key": place_key,
                "canonical_name": place["name"],
                "role": role,
                "role_goal": goal,
                "search_query": f"{place['name']} {suffix.replace('_', ' ')} real photograph",
                "source_pool_urls": place["sources"],
                "selected_source_page": None,
                "selection_status": "PENDING_LOCALIZATION",
                "local_original_path": f"assets/photos/original/{place_key}__{suffix}.jpg",
                "local_thumb_path": f"assets/photos/thumb/{place_key}__{suffix}.webp",
                "local_medium_path": f"assets/photos/medium/{place_key}__{suffix}.webp",
                "localization_status": "PENDING_LOCALIZATION",
                "sha256": None,
                "width": None,
                "height": None,
                "mime": None,
            })
    manifest.update({
        "required_places": 36,
        "photos_per_place": 3,
        "required_assets": 108,
        "localized_originals": 84,
        "localized_thumbnails": 84,
        "localized_medium": 84,
        "decodable_originals": 84,
        "deduped_assets": 84,
        "status": "EXPANDED_TO_108_PENDING_LOCALIZATION",
        "blocking_condition": "24 gap-audit photographs pending localization",
    })
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"assets": len(manifest["assets"]), "places": manifest["required_places"]}))


if __name__ == "__main__":
    main()
