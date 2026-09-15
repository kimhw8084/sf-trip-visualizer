"""Local USGS Topo mosaics for the map's fully offline basemap."""

import hashlib
import io
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/basemap"
OUT.mkdir(parents=True, exist_ok=True)
SERVICE = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}"
# Covers the actual 1440px map viewport at each region's default zoom, with a small margin.
AREAS = {
    "overall": (-127.90, 33.10, -114.60, 41.22, 7),
    "sf": (-122.77, 37.58, -122.11, 38.00, 12),
    "monterey": (-122.48, 36.23, -121.38, 36.93, 11),
    "yosemite": (-120.56, 37.07, -118.66, 38.25, 11),
}


def tile_x(lon, zoom):
    return math.floor((lon + 180) / 360 * 2**zoom)


def tile_y(lat, zoom):
    return math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2**zoom)


def lon_edge(x, zoom):
    return x / 2**zoom * 360 - 180


def lat_edge(y, zoom):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2**zoom))))


jobs = {}
for region, (west, south, east, north, zoom) in AREAS.items():
    x0, x1 = tile_x(west, zoom), tile_x(east, zoom)
    y0, y1 = tile_y(north, zoom), tile_y(south, zoom)
    jobs[region] = (zoom, x0, x1, y0, y1)


def get_tile(job):
    region, zoom, x, y = job
    url = SERVICE.format(z=zoom, x=x, y=y)
    for attempt in range(3):
        response = requests.get(url, timeout=20, headers={"User-Agent": "SFFamilyTripMap/1.0 (personal offline package)"})
        if response.status_code == 200:
            with Image.open(io.BytesIO(response.content)) as source:
                image = source.convert("RGB")
            if image.size == (256, 256):
                return region, x, y, image
    raise RuntimeError(f"Could not decode USGS tile {url}: HTTP {response.status_code}")


tiles = [(region, z, x, y) for region, (z, x0, x1, y0, y1) in jobs.items() for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
images = {region: Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256), "#f7f4eb") for region, (_, x0, x1, y0, y1) in jobs.items()}
print(f"Downloading {len(tiles)} USGS Topo tiles for four offline mosaics", flush=True)
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [executor.submit(get_tile, tile) for tile in tiles]
    for number, future in enumerate(as_completed(futures), 1):
        region, x, y, image = future.result()
        _, x0, _, y0, _ = jobs[region]
        images[region].paste(image, ((x - x0) * 256, (y - y0) * 256))
        if number % 40 == 0 or number == len(tiles):
            print(f"{number}/{len(tiles)}", flush=True)

manifest = {"source_service": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer", "source_documentation": "https://www.usgs.gov/faqs/what-are-base-map-services-or-urls-used-national-map", "source_credit": "USGS The National Map", "mosaics": []}
for region, image in images.items():
    zoom, x0, x1, y0, y1 = jobs[region]
    path = OUT / f"usgs_topo_{region}.webp"
    image.save(path, "WEBP", quality=88, method=6)
    west, east = lon_edge(x0, zoom), lon_edge(x1 + 1, zoom)
    north, south = lat_edge(y0, zoom), lat_edge(y1 + 1, zoom)
    manifest["mosaics"].append({
        "region": region, "local_path": str(path.relative_to(ROOT)), "source_tile_template": SERVICE,
        "source_zoom": zoom, "tile_range": {"x": [x0, x1], "y": [y0, y1]},
        "tile_count": (x1 - x0 + 1) * (y1 - y0 + 1), "pixel_size": list(image.size),
        "coordinates": [[west, north], [east, north], [east, south], [west, south]],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size,
    })
(ROOT / "manifests/offline_basemap_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"tile_count": len(tiles), "mosaics": [{"region": x["region"], "bytes": x["bytes"], "pixels": x["pixel_size"]} for x in manifest["mosaics"]]}, indent=2))
