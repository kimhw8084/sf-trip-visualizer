# SF / Monterey / Yosemite family-trip map

Open **`SF_Smart_Minority_Map_First_Standalone.html`** directly in a modern browser. The opening experience uses a real Golden Gate Bridge photograph while the local map initializes. Its default Smart map, road geometry, fonts, terrain relief, and all displayed photographs are embedded, so initial load makes **zero remote requests**. The standalone file is large (~235 MB); allow a few seconds for first render.

For the smaller modular edition, run `python3 scripts/serve_map.py --port 8765` from this folder and open `http://127.0.0.1:8765/index.html`. The local server supplies byte-range requests for `assets/vector/sf_trip.pmtiles`. Do not open the modular file with `file://`; use the standalone file for direct opening.

## Public version

The current `main` branch is published at **https://kimhw8084.github.io/sf-trip-visualizer/**. Every push to `main` automatically assembles the minimal modular runtime and deploys it through `.github/workflows/deploy-pages.yml`. The public build includes the real-photo thumbnails/derivatives and local Smart Map resources, while original photographs, QA screenshots, historical builds, and delivery ZIPs remain local.

## What is on the map

The application has 36 verified places, 108 real local photographs, 79 itinerary cards, 41 route legs, four independently switchable strategies, nine dates, three regions, Korean and English, and light and dark themes. English place names remain primary; Korean place names appear as subtitles in Korean mode.

The original 28-place Phase-9 map was reconciled against all 230 rows and 43 columns of `SF_Trip_FINAL_SELECTION_50Criteria_2026-09-13.xlsx`, then cross-checked against official destination and family sources. The audit found two workbook selections missing from the map—Presidio Tunnel Tops and Bixby Creek Bridge—and a more serious source-list blind spot: the workbook contained no PIER 39 or sea-lion row. The bounded supplement adds:

- PIER 39 Sea Lions at K-Dock (must)
- Presidio Tunnel Tops + Outpost (strong, recovery-gated)
- Bixby Creek Bridge (swap; replaces Carmel + 17-Mile Drive)
- Powell–Hyde Cable Car (swap; replaces Coit/Lombard and is stroller/queue-gated)
- Carmel-by-the-Sea + Carmel Beach (strong, using the existing reset window)
- Ghirardelli Square + Aquatic Park (energy-gated bonus)
- El Capitan Meadow (short, nap-gated strong stop)
- Old Fisherman’s Wharf Monterey (optional dinner)

The full reconciliation and keep/swap/skip rationale are in `LOCATION_COVERAGE_AUDIT.md` and `data/location_coverage_audit.json`.

## Reading and using it

A1 is blue, A2 green, B1 red, and B2 purple. Shared physical stops remain one marker, with a multi-color ring. Main route lines are solid; choose-one, conditional, bonus, and recovery-gap connections remain route-colored but use distinct dash patterns. Each casing repeats its colored line’s dash pattern, so no gray ghost route appears. Route layers remain present from zoom 0 through 24. Date chips, schedule cards, a persistent strategy/color legend, English/Korean labels, exact time, and tier are present on the map itself, so the itinerary remains readable with the right panel hidden.

Choosing a date or region fits the visible markers and their non-transfer route geometry inside the unobstructed map area. This is why the 10/8 Glacier Point day shows the complete Valley → Washburn → Glacier → Valley road loop rather than clipping it at the viewport edge. Long inter-region transfer lines remain visible without forcing a date’s destination markers into an unnecessarily broad fit.

Click a low-zoom cluster to zoom. Hover a desktop stop for a real-photo preview; on touch, tap once for the preview and use **Details** explicitly. Detail panels contain exactly three local photographs—HERO, EXPERIENCE, SCALE/CONTEXT—plus timing, “Why now?”, advantages, decision rules, route chips, provenance status for audited additions, and a Google Maps link. Identical cross-route timing/reason cards are deduplicated.

There are exactly two map choices: **Smart map** and **Satellite + labels**. Smart map is a local Protomaps/OSM vector extract with bundled labels and Yosemite terrain relief. It never silently changes to a raster while the user pans or zooms. If its local bundle is damaged, the application exposes a load error instead of swapping map identity. Satellite uses Esri imagery with the same local labels and requires a network connection; satellite tile failure returns to Smart map. USGS Topo and live OSM providers are removed. No Google tiles are copied or embedded.

The 41 route legs contain 39 locally cached OSM road/walk reference geometries plus two explicitly conceptual Alcatraz ferry relationships. Recovery gaps and choose-one links are labeled as such and are never presented as continuous sightseeing or mandatory travel. They are not live traffic, closure, or turn-by-turn directions. Recheck current conditions—especially Caltrans conditions before choosing Bixby.

## Reusing the visualizer

The build is data-driven: route controls come from `data.routes`, dates from `data.dates`, regions from `data.region_cfg`, and provider controls from `data.providers`. Marker visibility comes from route/date occurrences; timeline cards refer to marker keys; route legs define typed relationships. Replacing the trip data and matching local photo assets, then running `scripts/build_map_first.py`, produces the same interaction system without hard-coding four route IDs into the runtime. See `TRIP_VISUALIZER_SCHEMA.md` for the field contract, route semantics, asset naming, build steps, and QA invariants.

## Photos and evidence

`assets/photos/` contains 108 real place-specific originals, 108 WebP marker thumbnails, and 108 WebP medium/detail derivatives. The original Phase-2 obligation remains fully satisfied (84/84), and the eight audited additions contribute 24 more. `manifests/asset_manifest.json` preserves source page, direct image URL, creator/license metadata where available, dimensions, role, local paths, and SHA-256 hashes. There are no AI-generated images, generic placeholders, duplicate originals, or remote photo hotlinks.

`P0_PROOF_REPORT.md` records P0-1 through P0-12 individually. Browser evidence is in `QA/map_first/`, cross-browser and responsive screenshots are in `QA/screenshots/`, and photo contact sheets are in `QA/photo_review/`. The final package includes the authoritative JSON files, selection workbook, coordinate and coverage audits, route cache/manifest, provider configuration, source, build/test scripts, standalone HTML, and SHA-256 manifest.
