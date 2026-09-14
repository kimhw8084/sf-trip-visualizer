# Smart Minority SF Trip — Phase 8 Acceptance + Phase 9 Package Report
Generated: 2026-09-13

## Executive result

Phase 8 and Phase 9 are complete **for the current no-Phase-2 scope**. The acceptance suite now has evidence for every P0 row. Overall P0 is **not complete** because the 84 local real-photo binaries are still unavailable, which blocks P0-8, P0-9, and the photo portions of P0-10/P0-11. No requirement was relabeled to hide that dependency.

The final current-scope artifact is `SF_Smart_Minority_P0_Candidate.html`. It is a single-file build with bundled code/data/map runtime, zero place-photo network requests, and clean offline geographic fallback behavior.

## P0 proof table

| P0 | Status | Exact test | Quantitative result | Evidence | Remaining limitation |
|---|---|---|---|---|---|
| P0-1 | PASS* | Default offline geographic fallback rendered in a real MapLibre canvas; Light/OSM/Satellite each live-probed and on failure returned cleanly to offline. | 28 initial pins; 20 route legs; 1 MapLibre canvas; 0 external HTTP requests before provider probe; 3/3 remote failures cleanly fell back. | QA/screenshots/phase8_initial_overall.png; phase8_acceptance.json | *Closest available browser/preview-equivalent test. Final user-side ChatGPT Preview confirmation remains prudent. |
| P0-2 | PASS | Inspected provider manifest labels and failure domains; exercised each separately. | CARTO CDN, OSM tile.openstreetmap.org, and Esri ArcGIS Online are 3 distinct failure domains; labels name underlying providers accurately. | manifests/basemap_provider_manifest.json; phase8_acceptance.json | None material. |
| P0-3 | PASS | Actually activated Light, OSM, Satellite, waited for load/failure state, recorded requests and screenshots; also reused local positive ready fixture. | 3/3 remote providers live-tested; one probe request each; all failed in runner and stayed offline; local ready fixture = ready, canvas=1, 0 page errors. | QA/screenshots/phase8_provider_*.png; QA/provider_ready_fixture_qa.json | Remote providers are unavailable in this execution network, so they are correctly not presented as ready. |
| P0-4 | PASS | Independent coordinate audit preserved source and verified coordinates with decision and provenance for all current places. | 28/28 audited: 12 KEEP_EQUIVALENT, 9 CORRECT_TO_VERIFIED, 7 CORRECT_TO_OPERATIONAL_ARRIVAL; maximum correction 1244.6 m. | data/coordinate_audit.csv/json; regional QA screenshots | Street-level remote basemap unavailable; visual spot checks use bundled real geographic context plus verified points. |
| P0-5 | PASS | Static audit of app code plus live stress test. Plotly scattermap/MapLibre owns geographic rendering; no custom Mercator/tile math found. | Manual projection formula detected: false; 16 live pan/zoom cycles; 0 new runtime errors; 1 canvas retained. | QA/phase8_acceptance.json; src/app_phase7.js; QA/screenshots/phase8_stress_final.png | None material. |
| P0-6 | PASS | Opened initial all-route/all-date/overall state and inspected common-vs-divergence structure. | A1/A2/B1/B2 all ON; 28 unique stops; 20 classified connectors; 71 deduplicated timeline slots. | QA/screenshots/phase8_initial_overall.png; phase8_acceptance.json | Photo thumbnails remain deferred with Phase 2. |
| P0-7 | PASS (fallback path) | Audited all route legs. Exact router was unavailable, so no road geometry was fabricated; conceptual/car/walk/ferry relationships are visually subordinate and explicitly non-road/non-GPS claims. | 20/20 legs use conceptual or conceptual_transfer fallback; modes = drive/ferry/walk; 0 falsely claimed exact-routed legs; 20/20 semantically explicit as conceptual/non-road relationships. | data/route_geometry_manifest.json; QA screenshots | Exact road/walk/ferry polylines remain an upgrade if routing egress becomes available; current behavior matches the handoff fallback rule. |
| P0-8 | BLOCKED | Inspected 84-entry asset manifest and local filesystem for actual photo bytes. | 84/84 required slots exist in manifest; 0/84 localized originals; 0/84 thumbnails; 0/84 medium derivatives. | manifests/asset_manifest.json | Binary web-to-local transfer remains unavailable in this execution environment. No generated/fake replacement was used. |
| P0-9 | BLOCKED | Inspected marker implementation and DOM. | 28 unique markers work, but 0 real-photo thumbnail markers because P0-8 assets are absent. | QA/phase8_acceptance.json; src/app_phase7.js | Depends on Phase 2/P0-8. |
| P0-10 | BLOCKED (interaction passes) | Desktop/touch preview behavior tested. | Preview visible; title/Why-now present; touch path passes; 0 photo <img> because Phase 2 is frozen. | QA/phase6_7_final_qa.json; QA/screenshots/phase7_final_touch_390.png | Real-photo portion depends on P0-8. |
| P0-11 | BLOCKED (structure passes) | Common and divergent detail views tested for dedupe, timing, decision rules, maps link, and exactly three reserved photo roles. | Common stop: 4 route chips → 1 timing card; divergent Mariposa: 2 chips → 2 timing cards; 3 reserved photo roles; 0 real photo images. | QA/phase8_acceptance.json; QA/screenshots/phase7_final_detail_ferry.png | Actual 3-photo content depends on P0-8. |
| P0-12 | PASS | Ran consolidated acceptance suite, exhaustive state-matrix audit, provider tests, stress test, mobile/touch evidence reuse, and manual screenshot montage inspection. | 160 route/date/region combinations audited; real-control A1+10/9+Yosemite = 1 marker + 1 FLEX timeline row; 0 runtime errors; desktop/tablet/430/390 widths previously pass without overflow. | QA/phase8_acceptance.json; QA/phase8_visual_montage.jpg; this report | Overall P0 is NOT complete because P0-8 through photo-dependent P0-11 remain blocked. |

## Phase 8 consolidated QA

- Initial state: **28 markers**, **20 legs**, **71 timeline slots**, all four scenarios on.
- External HTTP requests before a provider probe: **0**.
- Exhaustive state matrix: **160** single-route/date/region states audited.
- Real control regression: A1 + 10/9 + Yosemite → **1 marker**, **1 timeline row**, FLEX detected = **True**.
- light: health **failed**, active provider after test **offline**, HTTP probes **1**, app errors **0**.
- osm: health **failed**, active provider after test **offline**, HTTP probes **1**, app errors **0**.
- satellite: health **failed**, active provider after test **offline**, HTTP probes **1**, app errors **0**.
- Pan/zoom stress: **16 cycles**, new errors **0**.
- Coordinate audit: **28/28** rows present and independently verified.
- Geometry audit: **20** legs; exact-routed **0**; conceptual fallback **20**; semantic explicitness **20/20**.
- Photo manifest: **84/84** slots defined; localized photo binaries **0/84**.

## Manual visual inspection

The Phase-8 screenshot montage was manually inspected after the automated suite. The initial overall view keeps the macro SF→Monterey→Yosemite structure legible; provider failures do not paint error tiles across the map; the composed Yosemite FLEX state remains readable; desktop and 390px phone layouts retain access to itinerary controls. The local fallback is intentionally minimalist at close zoom and is not presented as a street basemap.

## Phase 2 unblock attempts recorded

- Shell/Python/container outbound DNS cannot fetch image hosts.
- The dedicated container URL downloader also failed against a known real image URL.
- Headless Chromium direct-image navigation timed out in this network environment.
- GitHub binary file fetch and blob fetch reject/decode binary data; the GitHub contents-API path is rejected before exposing base64 image bytes.
- Web/image search can discover and preview real images, but it cannot write those image bytes into the local artifact filesystem in this session.
Therefore Phase 2 remains a genuine environment dependency, not an unattempted task.

## Completion statement

**Phase 8: complete. Phase 9: complete for the current artifact scope. Overall P0: not yet complete.** The exact remaining gate is Phase 2 localization of 84 real photographs, followed by replacement of temporary marker/preview/detail photo slots and a short delta acceptance rerun for P0-8 through P0-11.
