# Reusable trip-visualizer contract

## Canonical authority

The machine-readable authority map is `manifests/canonical_pipeline.json`. The current authored application dataset is `data/phase7_app_data.json`; `phase7` is a historical filename, not a permission to use a Phase-era build. The maintained source is rendered by `scripts/build_map_first.py` and orchestrated by `scripts/pipeline.py`.

`data/phase7_app_data.json` is the sole authored trip-truth source. Its `routes`,
`dates`, `region_cfg`, `markers`, `place_region`, `timeline`, `legs`,
`endpoint_anchors`, `replan_rules`, and `providers` fields drive the client. The
locked route/itinerary snapshots, canonical-place export, coordinate audits, and
location-gap audit are reference evidence; they corroborate the source but never
override it or drive a build. `data/translations.json`, route geometry, and asset
provider manifests are derived projections/evidence. `manifests/trip_freshness.json`
is the one source/recheck authority for time-varying decision facts and is not an
alternate itinerary source. `scripts/validate_trip_data.py` enforces these boundaries.

Normal build/check commands never write authored data. `data/translations.json`, `data/route_geometry_cache.json`, `data/route_geometry_manifest.json`, and the provider/photo manifests are derived inputs or evidence. The location-gap mutation is an explicit source-generation operation only:

```bash
python3 scripts/apply_location_gap_audit.py --write
```

Gate 3 refresh and validation use the canonical pipeline:

```bash
python3 scripts/pipeline.py fast
python3 scripts/pipeline.py qualify
python3 scripts/refresh_trip_data.py validate
python3 scripts/refresh_trip_data.py refresh --offline
```

For a pre-trip refresh, supply a reviewed machine-readable observation file to
`refresh_trip_data.py refresh --observations <file>`. Each observation must carry a
fact id, a genuine `observed_on` date when known, a source URL, certainty/status,
and is merged into the freshness manifest before the canonical build/check runs.
Without safe external retrieval, the workflow stays fail-closed as
`UNVERIFIED` / `RECHECK_REQUIRED`; it never invents a verification date.

## Core data

`data/phase7_app_data.json` supplies:

- `routes`: keyed strategies with color, pattern, title, and decision narrative;
- `dates`: ordered date keys with Korean and English labels;
- `region_cfg`: region centers, labels, and initial zooms;
- `markers`: exactly one record per physical place;
- `timeline`: itinerary cards whose `spatial_keys` point to marker keys; and
- `legs`: date- and route-scoped typed relationships between endpoints. Endpoints
  are either one physical `place_key` or an explicit `endpoint_anchors` entry such
  as a ferry embarkation or regional transfer anchor.

The maintained invariants are 39 markers, 67 timeline cards, 45 typed connectors, five routes (A–E), nine dates, three non-overall regions, and exactly the `vector` and `satellite` providers. `manifests/asset_manifest.json` supplies 117 place/roles as 117 total real local photographs: HERO, EXPERIENCE, and SCALE_CONTEXT for every place.

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

## Gate 4 runtime-resilience contract

`manifests/runtime_resilience_contract.json` is the single Gate 4 contract for
the four delivery forms and the two maintained providers. `vector` is the
explicit `smart-local-vector` identity: its PMTiles, fonts, sprites, terrain,
and local photo derivatives are critical local assets. Missing or corrupt local
assets are a qualification failure or a visible Smart-map failure; they never
authorize a remote substitute. Satellite is optional network behavior. Its
health probes, tile failures, bounded fallback, state preservation, and any
unverified external-provider success are recorded by
`scripts/qa_gate4_resilience.py` in `QA/release/gate4*.json`.

Gate 4 evidence is run by `scripts/pipeline.py fast` and `qualify`; public and
package hashes are added by the existing canonical assembly/package commands.
This contract is a production-readiness gate only and is not a production
release claim.
