"""Add attraction/NPS/photographer candidates for Commons coverage gaps."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

from discover_photos import OUT, ROOT, download_preview, sheet


SOURCES = {
    "exploratorium": [
        ("https://www.exploratorium.edu/", "https://www.exploratorium.edu/sites/default/files/East%20Gallery2960x453.jpg", "Current Pier 15 East Gallery"),
        ("https://ehdd.com/project/the-exploratorium-at-pier-15/", "https://ehdd.com/wp-content/uploads/2018/11/4-Exploratorium-BruceDamonte-e1543941464619.jpg", "Current Pier 15 exhibit hall"),
        ("https://blooloop.com/museum/in-depth/the-exploratorium/", "https://blooloop.com/media-library/gallery-at-exploratorium.jpg?id=56477394&quality=90&width=1200", "Pier 15 visitor gallery"),
    ],
    "cooks": [
        ("https://www.nps.gov/yose/planyourvisit/cooksmeadowtrail.htm", "https://www.nps.gov/yose/planyourvisit/images/IMG_6693edit.jpg?maxwidth=1200&autorotate=false", "Yosemite Falls from Cook's Meadow"),
        ("https://noahlangphotography.com/blog/cooks-meadow-loop-trail-yosemite-national-park", "https://images.squarespace-cdn.com/content/v1/6226f62738f4f73d2b353e79/669cd5ae-3047-4ff0-b4d9-b7d60692ddad/DSC08946.jpg?format=1600w", "Cook's Meadow boardwalk"),
        ("https://www.americansouthwest.net/california/yosemite/cooks-meadow-boardwalk_l.html", "https://www.americansouthwest.net/california/photographs700/cooks-meadow-boardwalk.jpg", "Cook's Meadow boardwalk in dry season"),
        ("https://noahlangphotography.com/blog/cooks-meadow-loop-trail-yosemite-national-park", "https://images.squarespace-cdn.com/content/v1/6226f62738f4f73d2b353e79/edb80937-1f43-41ed-b21b-5532ee216a5d/IMG_7651%2Bcopy.jpg?format=1600w", "Cook's Meadow trail"),
    ],
    "botanical": [
        ("https://gggp.org/san-francisco-botanical-garden/", "https://gggp.org/wp-content/uploads/2023/08/hero-sfbg.jpg", "Official botanical garden hero"),
        ("https://gggp.org/san-francisco-botanical-garden/", "https://gggp.org/wp-content/uploads/2023/08/sfbg-offset-image.jpg", "Official botanical garden view"),
        ("https://gggp.org/san-francisco-botanical-garden/", "https://gggp.org/wp-content/uploads/2023/11/garden_thumb_great_meadow.jpg", "Official great meadow"),
        ("https://gggp.org/san-francisco-botanical-garden/", "https://gggp.org/wp-content/uploads/2023/11/garden_thumb_childrens_garden.jpg", "Official children's garden"),
        ("https://gggp.org/san-francisco-botanical-garden/", "https://gggp.org/wp-content/uploads/2023/11/garden_thumb_moon_viewing_garden.jpg", "Official moon-viewing garden"),
        ("https://gggp.org/san-francisco-botanical-garden/", "https://gggp.org/wp-content/uploads/2023/11/garden_thumb_celebration_garden.jpg", "Official celebration garden"),
    ],
    "valley_view": [
        ("https://www.nps.gov/places/000/valley-view.htm", "https://www.nps.gov/common/uploads/cropped_image/primary/78716304-EC42-BF9C-50822593E30C0D3A.jpg?mode=crop&quality=90&width=1600", "NPS Valley View from Merced River"),
    ],
}


def page_images(url: str, predicate) -> list[tuple[str, str, str]]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    result = []
    for image in soup.find_all("img"):
        src = image.get("data-src") or image.get("src") or ""
        alt = image.get("alt") or ""
        if src and predicate(src, alt):
            result.append((url, urljoin(url, src), alt or src.rsplit("/", 1)[-1]))
    return result


def main() -> None:
    path = OUT / "candidates.json"
    all_candidates = json.loads(path.read_text())
    sources = {key: list(value) for key, value in SOURCES.items()}
    fortune_page = "https://www.goldengatefortunecookies.com/gallery-our-visitors"
    sources["fortune"] = page_images(fortune_page, lambda src, alt: "images.squarespace-cdn.com" in src and "Logo" not in src)[:38]
    valley_page = "https://www.nps.gov/yose/planyourvisit/yv.htm"
    sources["valley_view"] += page_images(valley_page, lambda src, alt: "Valley View" in alt or "Merced River" in alt)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; local SF family trip photo review)"})
    for place, rows in sources.items():
        items = all_candidates[place]
        seen = {x["source_url"] for x in items}
        place_dir = OUT / "previews" / place
        for page_url, source_url, description in rows:
            if source_url in seen:
                continue
            idx = len(items)
            preview_local = place_dir / f"{idx:02d}.jpg"
            if not download_preview(session, source_url, preview_local):
                print("failed", place, source_url, flush=True)
                continue
            with Image.open(preview_local) as image:
                width, height = image.size
            if width < 600 or height < 300:
                preview_local.unlink(missing_ok=True)
                continue
            items.append({
                "title": description,
                "page_url": page_url,
                "source_url": source_url,
                "preview_url": source_url,
                "width": width,
                "height": height,
                "description": description,
                "categories": "",
                "artist": "",
                "license": "see source page",
                "preview_local": str(preview_local.relative_to(ROOT)),
            })
            seen.add(source_url)
        sheet(place, items)
        all_candidates[place] = items
        path.write_text(json.dumps(all_candidates, ensure_ascii=False, indent=2))
        print(place, len(items), flush=True)


if __name__ == "__main__":
    main()
