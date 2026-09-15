# Reusable trip-visualizer contract

This application is a reusable, data-driven map shell. A future trip should replace the trip data, photo assets, translations, and cached route geometry—not fork the renderer.

## Core data

`data/phase7_app_data.json` supplies:

- `routes`: keyed route strategies with `color`, `pattern`, `title`, and `core_reason`.
- `dates`: ordered `key`, Korean `label`, and English `label_en` values.
- `region_cfg`: region keys with labels, centers, and initial zooms.
- `markers`: one record per physical place. Never duplicate a marker because several routes share it.
- `timeline`: ordered itinerary cards. `spatial_keys` link a card to zero or more marker keys.
- `legs`: date- and route-scoped connections between marker or transfer endpoints.
- `providers`: only the providers intentionally exposed in the interface.

Each marker occurrence must include `route`, `date`, `time`, `reason`, `advantage`, `status`, and `seq`. Place-level fields supply the summary, selection reasoning, Maps URL, decision rules, region, and local-photo status.

## Route semantics

Use `branch_kind` deliberately:

- `main`: normal sequence.
- `conditional`: runs only when its stated condition passes.
- `swap`: an alternative branch that replaces another stop or branch.
- `bonus`: optional addition when time/energy remains.
- `recovery`: a visible relationship across a meal, nap, hotel, or other long break; not continuous sightseeing.
- `choice`: connects mutually exclusive options; not a claim that both are visited.

Use `render_style: transfer_dots` only for inter-region transfers. Ferry legs are conceptual endpoint relationships unless a verified vessel track exists. Road/walk geometry is cached into `data/route_geometry_cache.json`; the application performs no runtime routing calls.

## Photo contract

Every place requires exactly three real local photographs:

- `HERO`: instant place identification.
- `EXPERIENCE`: what the visit feels like.
- `SCALE_CONTEXT`: spatial scale or surrounding context.

Paths follow `assets/photos/{original|thumb|medium}/{place_key}__{hero|experience|scale_context}.{ext}`. `manifests/asset_manifest.json` records the source page, direct image URL, creator/license metadata when available, local paths, dimensions, MIME type, visual-review note, and SHA-256 hashes. No remote photo is used at runtime.

## Build and verification

1. Update the trip data and translations.
2. Add the three local photo roles for every marker and refresh the asset manifest.
3. Run `python3 scripts/cache_route_geometry.py` while online.
4. Run `python3 scripts/refresh_map_first_manifests.py`.
5. Install `requirements-qa.txt`, then run `python3 scripts/build_map_first.py`.
6. Serve the modular build with `python3 scripts/serve_map.py --port 8766`, or open the standalone HTML directly.
7. Run the photo, continuity, interaction, 600-state, independent-P0, standalone, responsive, and cross-browser QA scripts.

The reusable invariants are: one marker per physical place; exact local-photo roles; no route layer zoom cliffs; no hidden Smart-map provider switch; fit all visible non-transfer geometry; no cross-date lines; complete Korean/English content; no mobile overflow; and explicit semantics for every non-literal connection.
