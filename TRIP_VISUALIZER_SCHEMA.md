# Reusable trip-visualizer contract

## Canonical authority

The machine-readable authority map is `manifests/canonical_pipeline.json`. Its `authority.active_trip_package` selects a complete trip package. The checked-in active package is `packages/sf-family/trip.json`; it selects the current authored application dataset at `data/phase7_app_data.json`. That historical data filename is an SF package detail, not the reusable contract. The shared renderer is built by `scripts/build_map_first.py` and orchestrated by `scripts/pipeline.py`.

Each package has one canonical authored itinerary source. For the active SF package, `data/phase7_app_data.json` is that source. Its `routes`,
`dates`, `region_cfg`, `markers`, `place_region`, `timeline`, `legs`,
`endpoint_anchors`, `replan_rules`, `trip_identity`, `operating_days`,
`travel_ranges`, `readiness_items`, `cost_cockpit`, and
`non_photo_itinerary_identities` fields drive the client. The
locked route/itinerary snapshots, canonical-place export, coordinate audits, and
location-gap audit are reference evidence; they corroborate the source but never
override it or drive a build. The package descriptor owns trip identity, display
title, slug, currency, canonical data path, derived projection paths, local
photo/map resources, provider configuration, freshness/source policy, and
artifact naming. Translations, route geometry, schedules, role matrices, photo
manifests, and freshness records are selected through its `projections` object.
Freshness remains the single source/recheck authority for time-varying decision
facts. `scripts/trip_package.py` validates the reusable package boundary;
`scripts/validate_trip_data.py` additionally enforces current SF itinerary and
CHG-63 truth laws.

Normal build/check commands never write authored data. Derived projections are
selected by the package descriptor. Superseded SF route-family/location-gap
generators are historical lineage and must not be run against the current trip;
they can restore retired route IDs and prior schedules.

## Trip package boundary

`packages/sf-family/trip.json` is the active package descriptor. It selects one
canonical itinerary source plus its translations, route roles/schedules/geometry,
freshness and research projections, photo root/manifest, local vector archive,
style resources, optional terrain, provider definitions, HTTPS source policies,
currency, bilingual title/subtitle, slug, and optional stable compatibility
filename. Paths stay inside the repository and required assets must exist.
Source policies permit only declared HTTPS hosts and paths; credentials, ports,
fragments, undeclared query keys, and links outside declared source classes are
rejected by the runtime URL gates.

Use `python3 scripts/build_map_first.py --package <descriptor> --output-dir <dir>`
to build any package. Omitting `--package` selects the active SF package. Generated
standalone names derive from the sanitized package slug; a descriptor may declare
a stable compatibility alias for existing release consumers. The synthetic
`packages/portability-fixture/trip.json` package is architecture evidence only;
the canonical fast path builds it with the same engine and checks its title,
identity, translation, route/date/region/currency/photo/map/provider/source policy
and isolation. It is visibly marked as QA-only and excluded from shipping.

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

The active SF package's canonical data supplies:

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

The active SF regression package has one itinerary (`A`), 39 photo-backed place
identities, 93 timeline cards, 24 typed connectors, and 11 dates (October 2–12).
It keeps the existing three non-overall regions. Provider IDs and configuration
are package-owned; the runtime requires a local `vector` provider and supports
any number of declared optional raster providers. Route identifiers come from
each package's canonical role/schedule source; the renderer supports one or
multiple routes. The active SF photo manifest supplies 117 real local
photographs: HERO, EXPERIENCE, and SCALE_CONTEXT for every active marker. A
future package supplies its own photo manifest and local derivatives.
Historical route evidence stays outside configured runtime.

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

Each descriptor declares its photo root and local thumbnail/medium directories.
Runtime uses local derivatives only. The selected photo manifest records source
page, direct image URL, creator/license metadata where available, local paths,
dimensions, MIME type, visual-review note, and SHA-256 hashes. No remote photo is
used at runtime.

## Canonical pipeline

```bash
python3 -m pip install -r requirements-qa.txt
python3 scripts/build_map_first.py --package packages/sf-family/trip.json --output-dir .build
python3 scripts/build_map_first.py --package packages/portability-fixture/trip.json --output-dir .build/portability-fixture
python3 scripts/pipeline.py fast
python3 scripts/pipeline.py qualify
python3 scripts/pipeline.py package
```

`fast` validates package schema, source/integrity/build invariants, runs both
packages through the same renderer to prove package isolation, protects
authored-input hashes, and compares a repeat active-package build. `qualify`
runs the decisive map-first, route/place role, geometry, standalone,
responsive/cross-browser, phone field-surface, and focused visual suites. It
writes current exact-candidate evidence to `QA/CHG-232/` and never rewrites
historical evidence.

Qualification components have a 300-second default timeout. A timeout is machine-recorded as `UNVERIFIED` and blocks release; `TRIP_QUALIFICATION_TIMEOUT_SECONDS` is available only to shorten local diagnostic runs.

The default generated modular artifact is `.build/modular/index.html`; serve it
with `python3 scripts/pipeline.py serve --port 8766`. The standalone file is
`.build/standalone/<package-slug>-standalone.html`; the active SF descriptor also
emits its declared historical alias for existing consumers. `package` requires
PASS qualification and produces `.release/package/` plus `.release/package.zip`
containing modular, standalone, public, source, manifests, and current evidence.

GitHub Pages runs the same exact-revision release command, checks the staged `.public-site/.release-provenance.json`, and uploads/deploys only after the qualification and provenance checks pass. Historical root HTML, `QA/final_*`, phase evidence, `build_final.py`, `package_final.py`, and provider-era scripts are retained for history but are not supported authority.

## Gate 4 runtime-resilience contract

`manifests/runtime_resilience_contract.json` defines Gate 4 behavior for the
delivery forms. Each package declares a local `vector` identity and its local map,
fonts, sprites, optional terrain, and photo derivatives as local assets. Missing
or corrupt local assets are a qualification failure or a visible Smart-map
failure; they never authorize a remote substitute. Package-declared raster
providers are optional network behavior. Their health probes, tile failures,
bounded fallback, state preservation, and any unverified external-provider
success are recorded by
`scripts/qa_gate4_resilience.py` in `QA/CHG-204/release/gate4*.json`.

Gate 4 evidence is run by `scripts/pipeline.py fast` and `qualify`; public and
package hashes are added by the existing canonical assembly/package commands.
This contract is a production-readiness gate only and is not a production
release claim.
