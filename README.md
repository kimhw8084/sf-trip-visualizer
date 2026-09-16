# SF / Monterey / Yosemite Smart Minority trip visualizer

This repository’s product is the Smart Minority family-trip decision system. The map renderer is reusable infrastructure; decision quality, resilient replanning, truthful route/geographic semantics, local-first Smart-map behavior, one physical-place identity, three real local photo roles, Korean/English, and touch/keyboard/responsive behavior are the product contract.

The maintained product currently contains 36 physical places, 108 real local photographs, 79 itinerary cards, 41 route legs, four route strategies, nine dates, three regions, Korean/English, light/dark, a local Smart map, optional Satellite + labels fallback, modular output, and standalone output.

## One supported path

The normal developer and release authority is `scripts/pipeline.py`. It composes the existing Python build and QA tools; no framework or manual release ritual is required.

```text
canonical authored source/data
        ↓
pipeline.py fast       source/schema/integrity/build invariants + reproducibility
        ↓
pipeline.py qualify    full map-first/photo/route/provider/interaction/browser evidence
        ↓
pipeline.py package    qualified modular + standalone + public package and ZIP
pipeline.py release    exact-SHA qualification + Pages assembly (CI path)
```

Install QA dependencies once with `python3 -m pip install -r requirements-qa.txt`.

- Fast deterministic validation: `python3 scripts/pipeline.py fast`
- Full qualification: `python3 scripts/pipeline.py qualify`
- Local modular preview after a build: `python3 scripts/pipeline.py serve --port 8766`
- Qualified package: `python3 scripts/pipeline.py package`
- Exact-revision release assembly: `python3 scripts/pipeline.py release --revision <git-sha>`

`qualify` writes machine-readable current evidence to `QA/release/qualification.json` and does not rewrite `P0_PROOF_REPORT.md` or the old `QA/final_*` evidence. Browser- or environment-specific failures remain failed/unverified gates; they are not converted into smoke-test success.

Each component has a 300-second bound by default. For local diagnostics only, `TRIP_QUALIFICATION_TIMEOUT_SECONDS` may shorten that bound; a timeout is recorded as `UNVERIFIED` and blocks release.

## Authority and data boundary

The complete authority map is [manifests/canonical_pipeline.json](manifests/canonical_pipeline.json). In particular, `data/phase7_app_data.json` is the current authored product dataset despite its historical filename. The current authored renderer inputs are `src/map_shell_template.html`, `src/app_phase7.js`, `src/app_phase7.css`, `src/map_first.css`, `src/vector_entry.js`, local vendor/runtime assets, the local vector/relief assets, and the audited source/selection inputs listed in the manifest.

Derived inputs are `data/translations.json`, `data/route_geometry_cache.json`, `data/route_geometry_manifest.json`, and the generated/provenance manifests. The explicit source-generation step `python3 scripts/apply_location_gap_audit.py --write` is allowed to update authored audit data; normal build, fast checks, qualification, packaging, and release never run it. The canonical build only reads authored inputs and derived inputs and writes `.build/`.

Generated locations are:

- `.build/modular/index.html` and its copied local runtime dependencies;
- `.build/standalone/SF_Smart_Minority_Map_First_Standalone.html`;
- `.public-site/`, including `.release-provenance.json`;
- `.release/` package output; and
- current machine-readable QA under `QA/release/` and `QA/map_first/`.

The build is reproducible enough for Project OS use: fast validation snapshots authored-input hashes, emits the build manifest, rebuilds into a temporary directory, and compares every generated output. It also checks the 36/108/79/41 product counts, route/date/region/provider contracts, exact photo roles, semantic route links, and duplicate physical-place keys.

## Local development and product behavior

Run `pipeline.py fast`, then serve with `pipeline.py serve`. Do not open the modular file with `file://`; the local server supplies byte-range requests for `assets/vector/sf_trip.pmtiles`. The standalone HTML in `.build/standalone/` is the direct-open edition and embeds the local vector archive, fonts/sprites, Yosemite relief, photo derivatives, and loading photograph.

The map has exactly two user-facing choices: Smart map and Satellite + labels. Smart map is the bundled Protomaps/OSM vector extract and never silently changes to a raster provider. If its local bundle is damaged, the app exposes a load error. Satellite uses Esri imagery with the same local labels and returns to Smart map if its tiles fail. Runtime routing is not performed: 39 legs use cached OSM reference geometry and two Alcatraz relationships remain explicitly conceptual ferry links.

Dates, regions, route controls, markers, timeline cards, route legs, providers, photo status, and replanning rules are data-driven. A marker is one physical place even when several routes share it. Each place has exactly HERO, EXPERIENCE, and SCALE_CONTEXT local photo roles. The renderer displays English primary names with Korean subtitles in Korean mode, route-colored semantics, exact route/date timing, and explicit recovery/choice/conditional labels.

## Historical and legacy boundaries

Root `index.html`, `index_map_first.html`, and `index_phase7.html`, `SF_Smart_Minority_P0_Candidate.html`, the old `QA/final_*`/phase evidence, `P0_PROOF_REPORT.*`, and the old final/provider-era build scripts are historical snapshots or deprecated entry points. They remain in Git for audit/history and are not current authority. `build_final.py`, `package_final.py`, `run_acceptance.py`, `run_live_providers.py`, and the 84-photo expansion script fail closed with a deprecation message. No supported workflow references them.

Historical P0 evidence records the revision and product state it originally tested. It is not rewritten to certify this change or any future revision. Current exact-revision qualification is recorded separately under `QA/release/`.

## Public release

GitHub Pages publication is repository-native through `.github/workflows/deploy-pages.yml`. A push to `main` checks out `${{ github.sha }}`, installs the QA dependencies, runs `python3 scripts/pipeline.py release --revision "$GITHUB_SHA"`, verifies the staged artifact’s SHA/provenance, uploads `.public-site/`, and only then deploys. Assembly alone cannot deploy. The public artifact contains the modular runtime and local photo/map derivatives; original photos, screenshots, historical builds, and delivery ZIPs remain local or in the package as appropriate.

This is Production Readiness Gate 2 (canonical build/QA/packaging/release authority), not a claim of production readiness. Public photo-rights certification, full trip-data freshness, broad UX redesign, and security hardening remain separate gates unless explicitly scoped later.

See [TRIP_VISUALIZER_SCHEMA.md](TRIP_VISUALIZER_SCHEMA.md) for the data contract and [manifests/canonical_pipeline.json](manifests/canonical_pipeline.json) for the source/output/evidence inventory.
