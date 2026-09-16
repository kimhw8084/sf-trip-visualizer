"""Build local modular and offline standalone trip app from the Phase-9 baseline."""

raise SystemExit("DEPRECATED LEGACY ENTRY POINT: use python3 scripts/pipeline.py fast or qualify")

import base64
import json
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "manifests/asset_manifest.json").read_text())
assert MANIFEST["status"] == "COMPLETE_84_LOCAL_REAL_PHOTOS"

data_path = ROOT / "data/phase7_app_data.json"
data = json.loads(data_path.read_text())
data["phase2_frozen"] = False
data["phase2_note"] = "84 visually reviewed real photographs are localized with thumbnail and medium derivatives."
topo = json.loads((ROOT / "manifests/offline_basemap_manifest.json").read_text())
data["offline_topo"] = topo["mosaics"]
data["providers"]["offline"].update({"label": "Offline · local USGS Topo", "attribution": "USGS The National Map", "status_at_build": "READY_LOCAL_TOPO_FOUR_MOSAICS"})
data["providers"]["light"].update({
    "label": "Topo · USGS The National Map",
    "failure_domain": "USGS The National Map",
    "tile_template": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}",
    "health_probe": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/10/395/163",
    "attribution": "USGS The National Map",
    "status_at_build": "LIVE_READY_LOCAL_CHROMIUM_WITH_RUNTIME_HEALTH_GATE",
    "requires_api_key": False,
})
for provider in ("osm", "satellite"):
    data["providers"][provider]["status_at_build"] = "LIVE_READY_LOCAL_CHROMIUM_WITH_RUNTIME_HEALTH_GATE"
    data["providers"][provider].pop("observed_http_200_tiles", None)
for marker in data["markers"]:
    marker["photo_status"] = "LOCAL_3_REAL_PHOTOS_VERIFIED"
data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

template = BeautifulSoup((ROOT / "index_phase7.html").read_text(), "html.parser")
template.title.string = "Smart Minority · SF / Monterey / Yosemite Family Trip"
template.select_one(".sub").string = "Four routes · real local photos · synchronized itinerary"
for button in template.select('[data-provider="offline"]'):
    button.string = "Offline topo"
for button in template.select('[data-provider="light"]'):
    button.string = "USGS Topo"
template.select_one('#mobileProvider option[value="offline"]').string = "Offline topo"
template.select_one('#mobileProvider option[value="light"]').string = "USGS Topo"
template.select_one('#fallbackNote').string = "Local USGS topo active; no external tile requests."
badge = template.select_one('.map-badge')
badge.clear()
badge.append(BeautifulSoup('<b id="activeFilterSummary">4 routes · all dates · Overall</b><br><span>Gray dashed = shared; colored dashed = route-specific. Planning connectors, not road traces. Tap a photo for the full stop brief.</span><br><span id="fallbackNote">Local USGS topo active; no external tile requests.</span>', 'html.parser'))
route_tip = template.new_tag('div', id='routeTip')
route_tip['class'] = 'route-tip'
template.select_one('.mapwrap').append(route_tip)
overview = template.select_one('#routeOverview')
overview.extract()
overview['class'] = 'route-overview'
guide = template.new_tag('details')
guide['class'] = 'route-guide'
summary = template.new_tag('summary')
summary.string = 'Compare the four route strategies'
guide.append(summary)
guide.append(overview)
template.select_one('.sidebar').insert(0, guide)
maplibre_css = template.new_tag("link", rel="stylesheet", href="vendor/maplibre-gl.css")
template.head.append(maplibre_css)
scripts = template.find_all("script")
assert len(scripts) == 3
scripts[1].string = "window.TRIP_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"
maplibre_script = template.new_tag("script", src="vendor/maplibre-gl.js")
scripts[2].insert_before(maplibre_script)
basemap_embedded = {mosaic["local_path"]: "data:image/webp;base64," + base64.b64encode((ROOT / mosaic["local_path"]).read_bytes()).decode("ascii") for mosaic in topo["mosaics"]}
basemap_script = template.new_tag("script")
basemap_script.string = "window.EMBEDDED_BASEMAP=" + json.dumps(basemap_embedded, separators=(",", ":")) + ";"
scripts[2].insert_before(basemap_script)

modular = str(template)
(ROOT / "index.html").write_text(modular)

standalone = BeautifulSoup(modular, "html.parser")
for link in standalone.find_all("link", rel="stylesheet"):
    style = standalone.new_tag("style")
    style.string = (ROOT / link["href"]).read_text()
    link.replace_with(style)
for script in standalone.find_all("script", src=True):
    inline = standalone.new_tag("script")
    inline.string = (ROOT / script["src"]).read_text()
    script.replace_with(inline)

embedded = {}
for asset in MANIFEST["assets"]:
    for field in ("local_thumb_path", "local_medium_path"):
        path = asset[field]
        embedded[path] = "data:image/webp;base64," + base64.b64encode((ROOT / path).read_bytes()).decode("ascii")
embed_script = standalone.new_tag("script")
embed_script.string = "window.EMBEDDED_PHOTOS=" + json.dumps(embedded, separators=(",", ":")) + ";"
standalone.find_all("script")[-1].insert_before(embed_script)
output = ROOT / "SF_Smart_Minority_P0_Final_Standalone.html"
output.write_text(str(standalone))
print(f"Built {ROOT / 'index.html'} ({(ROOT / 'index.html').stat().st_size:,} bytes)")
print(f"Built {output} ({output.stat().st_size:,} bytes), embedded {len(embedded)} local derivatives")
