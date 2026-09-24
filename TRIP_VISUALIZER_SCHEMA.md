# Reusable trip-visualizer contract

## Canonical authority

The machine-readable authority map is `manifests/canonical_pipeline.json`. The current authored application dataset is `data/phase7_app_data.json`; `phase7` is a historical filename, not a permission to use a Phase-era build. The maintained source is rendered by `scripts/build_map_first.py` and orchestrated by `scripts/pipeline.py`.

`data/phase7_app_data.json` is the sole authored trip-truth source. Its `routes`,
`dates`, `region_cfg`, `markers`, `place_region`, `timeline`, `legs`,
`endpoint_anchors`, `replan_rules`, `providers`, `trip_identity`, `operating_days`,
`travel_ranges`, `readiness_items`, `cost_cockpit`, and
`non_photo_itinerary_identities` fields drive the client. The
locked route/itinerary snapshots, canonical-place export, coordinate audits, and
location-gap audit are reference evidence; they corroborate the source but never
override it or drive a build. `data/translations.json`, route geometry, and asset
provider manifests are derived projections/evidence. `manifests/trip_freshness.json`
is the one source/recheck authority for time-varying decision facts and is not an
alternate itinerary source. `scripts/validate_trip_data.py` enforces these boundaries.

Normal build/check commands never write authored data. `data/translations.json`, `data/route_geometry_cache.json`, `data/route_geometry_manifest.json`, and the provider/photo manifests are derived inputs or evidence. Superseded route-family/location-gap generators are classified as historical lineage and must not be run against the current trip; they can restore retired route IDs and prior schedules.

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
  as a ferry embarkation or regional transfer anchor;
- `operating_days`: owner-authored day summaries for departure, recovery/nap,
  preparation, and plan invalidators;
- `travel_ranges`: static schedule-derived planning windows with reference
  duration and schedule buffer represented separately;
- `readiness_items` and `cost_cockpit`: sourced prerequisites, dynamic fee
  semantics, lower-bound scenarios, and optional cost categories; and
- `non_photo_itinerary_identities`: physical activities that remain in the
  itinerary without a public map marker when the photo-rights contract is unmet.

The configured 2026 trip has one active itinerary (`A`), 39 photo-backed place
identities, 77 timeline cards, 32 typed connectors, and 11 dates (October 2–12).
It keeps the existing three non-overall regions and the `vector` / `satellite`
providers. Route identifiers come from the canonical role/schedule source; the
renderer supports a one-route trip without a comparison surface.
`manifests/asset_manifest.json` supplies 117 real local photographs: HERO,
EXPERIENCE, and SCALE_CONTEXT for every active marker. Historical route evidence
stays outside configured runtime.

## Final itinerary, recovery, and privacy

Recovery, transfers, and naps are itinerary semantics rather than attraction
dwell. `operating_days` carries each day's leave time, first/second nap or
protected lodging recovery, preparation, and invalidators. Material driving
departure cards show a live-navigation recheck. `travel_ranges` must identify
static planning ranges, keep reference/baseline duration separate from the
schedule window and its buffer, and never imply live traffic, turn-by-turn
authority, or Google routing.

The active dataset may identify public-safe lodging only as Mill Valley lodging
(Oct 2–6), Stage Coach Lodge, Monterey (Oct 6–7), Yosemite West lodging
(Oct 7–9), and Foster City lodging (Oct 9–12), with authored check-in/out and
designated parking facts. Private residential lodging street addresses,
residential coordinates, and private future occupancy details must not appear in
source, generated outputs, Pages, packages, standalone HTML, route endpoints,
labels, screenshots, fixtures, logs, or evidence. A lodging is not a sightseeing
marker or photo identity. `scripts/security_privacy.py` scans text across source,
QA/evidence, and generated artifacts with redacted findings; it separately
rejects residential place labels, private location fields, and residential route
endpoints.

## Readiness and costs

Each applicable `readiness_items` record carries official source URLs, research
date, confidence, recheck timing, prerequisite severity (`required`,
`strongly_recommended`, `optional`, `recheck_only`), fee semantics (`fixed`,
`starting`, `estimated`, `variable`, `conditional`, `included`, `free`), generic
parking guidance, baby/mobility guidance, and a place, active leg, or
logistics-only identity link. Dynamic and starting prices stay explicitly
unfinalized.

`cost_cockpit.scenarios` contains four user-selected analysis scenarios as lower
bounds, never quotations or an inferred residency choice.
`variable_checkout_required` and `optional_convenience` keep unresolved fees and
optional parking separate. Scenario lines are unique and their cent amounts
must sum to `lower_bound_cents`. Food, fuel, lodging, and base rental rate stay
excluded. Checklist values (`prepared`, `user_marked_booked`,
`user_marked_paid`) are local state scoped to `trip_identity`; they do not claim
an external booking or payment. Cost and readiness copy must be complete in
Korean and English.

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

`fast` validates source/schema/integrity/build invariants, protects authored-input hashes, and compares a repeat build. `qualify` runs the decisive map-first, single-route, place-role, geometry, standalone, responsive/cross-browser, and focused visual suites. It writes current exact-candidate evidence to `QA/CHG-204/` and never rewrites historical evidence.

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
`scripts/qa_gate4_resilience.py` in `QA/CHG-204/release/gate4*.json`.

Gate 4 evidence is run by `scripts/pipeline.py fast` and `qualify`; public and
package hashes are added by the existing canonical assembly/package commands.
This contract is a production-readiness gate only and is not a production
release claim.
