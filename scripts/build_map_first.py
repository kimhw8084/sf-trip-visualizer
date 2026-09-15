"""Build the bilingual map-first modular app and its fully local standalone edition."""

import base64
import json
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "data/phase7_app_data.json").read_text())
photo_manifest = json.loads((ROOT / "manifests/asset_manifest.json").read_text())
place_count = len(data["markers"])
photo_count = len(photo_manifest["assets"])
data["providers"]["vector"] = {
    "label": "Local Protomaps vector · OpenStreetMap data",
    "failure_domain": "local bundled PMTiles",
    "attribution": "© OpenStreetMap contributors · Protomaps",
    "requires_api_key": False,
    "status_at_build": "LOCAL_VECTOR_PM TILES_READY".replace(" ", ""),
}
data["providers"] = {key: value for key, value in data["providers"].items() if key in {"vector", "satellite"}}
data["phase2_frozen"] = False
data["phase2_note"] = f"{photo_count} local real photographs for {place_count} places, with local thumbnails and medium derivatives."
geometry = json.loads((ROOT / "data/route_geometry_cache.json").read_text())
translations = json.loads((ROOT / "data/translations.json").read_text())

template = BeautifulSoup((ROOT / "src/map_shell_template.html").read_text(), "html.parser")
template.title.string = "Smart Minority · SF / Monterey / Yosemite Map"
template.select_one(".sub")["data-i18n"] = "subtitle"
template.select_one(".sub").string = f"Four routes · nine days · {photo_count} real photos · {place_count} verified places"
for label in template.select(".group-label"):
    key = label.get_text(strip=True).lower()
    label["data-i18n"] = key
route_group = template.select_one("[data-route]").parent
for button in route_group.select("[data-route]"):
    button.decompose()
for route, meta in data["routes"].items():
    pair = template.new_tag("span", attrs={"class": "route-control-pair"})
    button = template.new_tag("button", attrs={"class": "ctl routeCtl active", "data-route": route, "aria-pressed": "true"})
    swatch = template.new_tag("span", attrs={"class": f'route-swatch {meta.get("pattern", "solid")}', "style": f'color:{meta["color"]}'})
    button.append(swatch)
    button.append(route)
    info = template.new_tag("button", attrs={"class": "route-info", "data-route-info": route, "type": "button", "aria-label": f"Explain route {route}", "aria-expanded": "false"})
    info.string = "i"
    pair.append(button)
    pair.append(info)
    route_group.append(pair)
for select_id in ("dateSelect", "mobileDate"):
    select = template.select_one(f"#{select_id}")
    select.clear()
    all_option = template.new_tag("option", value="all")
    all_option.string = "All dates"
    select.append(all_option)
    for item in data["dates"]:
        option = template.new_tag("option", value=item["key"])
        option.string = item["label"]
        select.append(option)
region_group = template.select_one("[data-region]").parent
for button in region_group.select("[data-region]"):
    button.decompose()
mobile_region = template.select_one("#mobileRegion")
mobile_region.clear()
for index, (region, meta) in enumerate(data["region_cfg"].items()):
    button = template.new_tag("button", attrs={"class": "ctl active" if index == 0 else "ctl", "data-region": region, "data-i18n": region, "aria-pressed": "true" if index == 0 else "false"})
    button.string = meta["label"]
    region_group.append(button)
    option = template.new_tag("option", value=region)
    option.string = meta["label"]
    mobile_region.append(option)
provider_group = template.select_one("[data-provider]").parent
for button in provider_group.select("[data-provider]"):
    button.decompose()
mobile_provider = template.select_one("#mobileProvider")
mobile_provider.clear()
for index, provider in enumerate(data["providers"]):
    label = "Smart map" if provider == "vector" else "Satellite + labels"
    button = template.new_tag("button", attrs={"class": "ctl active" if index == 0 else "ctl", "data-provider": provider, "data-i18n": provider})
    button.string = label
    provider_group.append(button)
    option = template.new_tag("option", value=provider)
    option.string = label
    mobile_provider.append(option)
for tab in template.select(".tab"):
    tab["data-i18n"] = tab["data-tab"]
template.select_one(".route-guide") if template.select_one(".route-guide") else None
overview = template.select_one("#routeOverview")
overview.extract()
overview["class"] = "route-overview"
guide = template.new_tag("details", attrs={"class": "route-guide"})
guide_summary = template.new_tag("summary", attrs={"data-i18n": "compare"})
guide_summary.string = "Compare four strategies"
guide.append(guide_summary)
guide.append(overview)
template.select_one(".sidebar").insert(0, guide)
actions = template.new_tag("div", attrs={"class": "utility-actions"})
for button_id, text in (("themeToggle", "☾ Dark"), ("langToggle", "EN"), ("panelToggle", "Hide panel")):
    button = template.new_tag("button", id=button_id, attrs={"class": "utility-button", "type": "button"})
    button.string = text
    actions.append(button)
template.select_one(".provider-state").insert_before(actions)
mapwrap = template.select_one(".mapwrap")
for tag, ident, cls in (("div", "dateRibbon", "date-ribbon"), ("div", "mapFocus", "map-focus"), ("div", "mapSchedule", "map-schedule"), ("div", "routeTip", "route-tip")):
    el = template.new_tag(tag, id=ident, attrs={"class": cls})
    mapwrap.append(el)
badge = template.select_one(".map-badge")
badge.clear()
badge.append(BeautifulSoup('<b id="activeFilterSummary"></b><div id="mapRouteLegend" class="map-route-legend"></div><span data-i18n="conceptual"></span><span id="fallbackNote"></span>', "html.parser"))
loading = BeautifulSoup(
    '<div id="loadingScreen" role="status" aria-live="polite">'
    '<img id="loadingHero" class="loading-hero" src="assets/photos/medium/ggb__hero.webp" alt="Golden Gate Bridge">'
    '<div class="loading-shade"></div><div class="loading-card">'
    '<div class="loading-kicker">SMART MINORITY · FAMILY FIELD MAP</div>'
    '<div class="loading-title">여행 전체를<br>한눈에 연결합니다</div>'
    '<div class="loading-subtitle">Connecting every day, route, decision, and real photograph into one field-ready map.</div>'
    '<div class="loading-progress" aria-hidden="true"></div>'
    '<div id="loadingStatus" class="loading-status">로컬 스마트 지도와 실제 사진을 준비하는 중…</div>'
    f'<div class="loading-foot"><span>{place_count} VERIFIED PLACES</span><span>{photo_count} LOCAL PHOTOS</span><span>4 ROUTE STRATEGIES</span></div>'
    '</div></div>',
    "html.parser",
)
template.body.insert(0, loading)
early_script = template.new_tag("script")
early_script.string = "window.__tripLoadStarted=performance.now();try{document.documentElement.dataset.theme=localStorage.getItem('trip_theme')||'light'}catch{document.documentElement.dataset.theme='light'}"
template.head.insert(0, early_script)
for href in ("vendor/maplibre-gl.css", "src/map_first.css"):
    template.head.append(template.new_tag("link", rel="stylesheet", href=href))
scripts = [script for script in template.find_all("script") if script is not early_script]
assert len(scripts) == 3
scripts[0].decompose()  # MapLibre owns map projection, pan, zoom, labels, and routes directly.
scripts[1].string = "window.TRIP_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"
for name, payload in (("TRIP_ROUTE_GEOMETRY", geometry), ("TRIP_I18N", translations)):
    script = template.new_tag("script")
    script.string = f"window.{name}=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";"
    scripts[2].insert_before(script)
for src in ("vendor/maplibre-gl.js", "vendor/trip-vector.js"):
    scripts[2].insert_before(template.new_tag("script", src=src))
scripts[2].insert_before(template.new_tag("script", id="embeddedVector"))
modular = str(template)
(ROOT / "index_map_first.html").write_text(modular)
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
hillshade_path = ROOT / "assets/vector/yosemite_hillshade_shadow.webp"
embed_hillshade = standalone.new_tag("script")
embed_hillshade.string = "window.EMBEDDED_HILLSHADE=" + json.dumps(
    "data:image/webp;base64," + base64.b64encode(hillshade_path.read_bytes()).decode("ascii")
) + ";"
standalone.find_all("script")[-1].insert_before(embed_hillshade)
photos = {}
for asset in photo_manifest["assets"]:
    for field in ("local_thumb_path", "local_medium_path"):
        path = asset[field]
        photos[path] = "data:image/webp;base64," + base64.b64encode((ROOT / path).read_bytes()).decode("ascii")
embed_photos = standalone.new_tag("script")
embed_photos.string = "window.EMBEDDED_PHOTOS=" + json.dumps(photos, separators=(",", ":")) + ";"
standalone.find_all("script")[-1].insert_before(embed_photos)
loading_path = ROOT / "assets/photos/medium/ggb__hero.webp"
standalone.select_one("#loadingHero")["src"] = "data:image/webp;base64," + base64.b64encode(loading_path.read_bytes()).decode("ascii")
map_assets = {}
for path in sorted((ROOT / "assets/vector/fonts").rglob("*.pbf")) + sorted((ROOT / "assets/vector/sprites").glob("*")):
    map_assets[str(path.relative_to(ROOT))] = base64.b64encode(path.read_bytes()).decode("ascii")
embed_assets = standalone.new_tag("script")
embed_assets.string = "window.EMBEDDED_MAP_ASSETS=" + json.dumps(map_assets, separators=(",", ":")) + ";"
standalone.find_all("script")[-1].insert_before(embed_assets)
standalone_text = str(standalone)
vector_base64 = base64.b64encode((ROOT / "assets/vector/sf_trip.pmtiles").read_bytes()).decode("ascii")
standalone_text = standalone_text.replace('<script id="embeddedVector"></script>', '<script>window.EMBEDDED_VECTOR="' + vector_base64 + '";</script>')
output = ROOT / "SF_Smart_Minority_Map_First_Standalone.html"
output.write_text(standalone_text)
print(f"Built index_map_first.html ({(ROOT / 'index_map_first.html').stat().st_size:,} bytes)")
print(f"Built {output.name} ({output.stat().st_size:,} bytes), {len(photos)} local derivatives, {len(map_assets)} local map assets")
