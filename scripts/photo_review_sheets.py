"""Render localized images in place/role order for final visual QA."""

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
assets = json.loads((ROOT / "manifests/asset_manifest.json").read_text())["assets"]
keys = list(dict.fromkeys(a["place_key"] for a in assets))
out = ROOT / "QA/photo_review"
out.mkdir(parents=True, exist_ok=True)
font = ImageFont.load_default()
rows_per_page = 12
pages = (len(keys) + rows_per_page - 1) // rows_per_page
for page in range(pages):
    page_keys = keys[page * rows_per_page:(page + 1) * rows_per_page]
    sheet = Image.new("RGB", (1140, len(page_keys) * 112), "#ffffff")
    draw = ImageDraw.Draw(sheet)
    for row, key in enumerate(page_keys):
        draw.text((5, row * 112 + 2), key, fill="#101828", font=font)
        for col, role in enumerate(("HERO", "EXPERIENCE", "SCALE_CONTEXT")):
            asset = next(a for a in assets if a["place_key"] == key and a["role"] == role)
            with Image.open(ROOT / asset["local_medium_path"]) as source:
                image = source.copy()
            image.thumbnail((360, 86))
            x, y = col * 380 + 10, row * 112 + 16
            sheet.paste(image, (x, y))
            draw.text((x + 2, y + 88), role, fill="#475467", font=font)
    path = out / f"localized_{len(assets)}_page_{page + 1}.jpg"
    sheet.save(path, quality=89)
    print(path.relative_to(ROOT))
