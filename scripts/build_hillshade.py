"""Convert official USGS 3DEP relief into a transparent map shadow overlay."""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "assets/vector/yosemite_hillshade_source.png"
output = ROOT / "assets/vector/yosemite_hillshade_shadow.webp"
image = Image.open(source).convert("L")
alpha = image.point(lambda value: max(0, min(130, int((248 - value) * 1.15))))
shadow = Image.new("RGBA", image.size, (22, 42, 51, 0))
shadow.putalpha(alpha)
shadow.save(output, "WEBP", lossless=True, method=6)
print(f"USGS hillshade: {image.width}×{image.height}, {output.stat().st_size:,} bytes")
