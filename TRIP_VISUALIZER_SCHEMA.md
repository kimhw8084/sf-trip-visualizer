# Reusable trip-visualizer contract

## Canonical authority

The machine-readable authority map is `manifests/canonical_pipeline.json`. The current authored application dataset is `data/phase7_app_data.json`; `phase7` is a historical filename, not a permission to use a Phase-era build. The maintained source is rendered by `scripts/build_map_first.py` and orchestrated by `scripts/pipeline.py`.

Normal build/check commands never write authored data. `data/translations.json`, `data/route_geometry_cache.json`, `data/route_geometry_manifest.json`, and the provider/photo manifests are derived inputs or evidence. The location-gap mutation is an explicit source-generation operation only:

```bash
python3 scripts/apply_location_gap_audit.py --write
```

## Core data

`data/phase7_app_data.json` supplies:

- `routes`: keyed strategies with color, pattern, title, and decision narrative;
- `dates`: ordered date keys with Korean and English labels;
- `region_cfg`: region centers, labels, and initial zooms;
- `markers`: exactly one record per physical place;
- `timeline`: itinerary cards whose `spatial_keys` point to marker keys; and
- `legs`: date- and route-scoped typed relationships between endpoints.

The maintained invariants are 36 markers, 79 timeline cards, 41 legs, four routes, nine dates, three non-overall regions, and exactly the `vector` and `satellite` providers. `manifests/asset_manifest.json` supplies 108 places/roles as 108 total real local photographs: HERO, EXPERIENCE, and SCALE_CONTEXT for every place.

## Route semantics

Use `branch_kind` deliberately:

- `main`: normal sequence;
- `conditional`: runs only when its condition passes;
- `swap`: an alternative branch replacing another stop or branch;
- `bonus`: optional if time/energy remains;
- `recovery`: a visible relationship across a meal, nap, hotel, or other long break; not continuous sightseeing; and
- `choice`: mutually exclusive options; not a claim that both are visited.

Use `render_style: transfer_dots` only for inter-region transfers. Ferry legs are conceptual endpoint relationships unless a verified vessel track exists. Road/walk geometry is cached in `data/route_geometry_cache.json`; the app performs no runtime routing calls. Cached OSM geometry is reference planning geometry, not live traffic, closure, or turn-by-turn navigation.

## Photo contract

Paths follow `assets/photos/{original|thumb|medium}/{place_key}__{hero|experience|scale_context}.{ext}`. Runtime uses local thumbnail/medium derivatives only. The asset manifest records source page, direct image URL, creator/license metadata where available, local paths, dimensions, MIME type, visual-review note, and SHA-256 hashes. No remote photo is used at runtime.

## Canonical pipeline

```bash
python3 -m pip install -r requirements-qa.txt
python3 scripts/pipeline.py fast
python3 scripts/pipeline.py qualify
python3 scripts/pipeline.py package
```

`fast` validates source/schema/integrity/build invariants, protects authored-input hashes, and compares a repeat build. `qualify` runs the existing decisive map-first smoke/full/P0/location-gap/interaction/route-panel/route-continuity suites, photo integrity, 600-state exhaustive rendering, standalone, responsive/cross-browser, and focused visual evidence. It writes a current report to `QA/release/qualification.json` and never rewrites historical P0 evidence.

Qualification components have a 300-second default timeout. A timeout is machine-recorded as `UNVERIFIED` and blocks release; `TRIP_QUALIFICATION_TIMEOUT_SECONDS` is available only to shorten local diagnostic runs.

The generated modular artifact is `.build/modular/index.html`; serve it with `python3 scripts/pipeline.py serve --port 8766`. The direct-open artifact is `.build/standalone/SF_Smart_Minority_Map_First_Standalone.html`. `package` requires PASS qualification and produces `.release/package/` plus `.release/package.zip` containing modular, standalone, public, source, manifests, and current evidence.

GitHub Pages runs the same exact-revision release command, checks the staged `.public-site/.release-provenance.json`, and uploads/deploys only after the qualification and provenance checks pass. Historical root HTML, `QA/final_*`, phase evidence, `build_final.py`, `package_final.py`, and provider-era scripts are retained for history but are not supported authority.
