# CHG-232 BUILD record

## Candidate

- Repository: `kimhw8084/sf-trip-visualizer`
- Branch: `codex/sf-trip-visualizer-phone-only-portable-trip-package-r1`
- Candidate: `0fd8a4c52c53824ad1c304625ff2d70a87420ac5`
- Tree: `c91b754b0c719f7ebe09961736ef659bbe6063b9`
- Exact predecessor `b260a0b4c38220f89af2e3b6772c46b5afc63c42` is an ancestor.
- Qualification binds the exact committed source tree and reports its source checkout clean. The full run leaves generated/updated QA files in the raw Git status; no source or package files changed after this candidate commit.
- Complete changed-path inventory against the predecessor: [changed_files.txt](changed_files.txt) (96 paths, including the fixture's synthetic local map and photo bundle).

## Package boundary

The canonical selector is `manifests/canonical_pipeline.json` → `packages/sf-family/trip.json`. `scripts/trip_package.py` loads and validates the versioned package descriptor before build output is emitted. The descriptor owns trip identity/title/slug, canonical data and translation paths, currency, photo root/manifest, local vector map and style resources, terrain/context assets, geometry and freshness projections, provider configuration, source URL policy, and generated artifact names.

Each package has one authored `trip-data.json`; translations, geometry, route/provider/map/photo/freshness manifests are package-scoped projections. The checked-in SF package remains the default. The nonshipping fixture is explicitly marked as QA-only.

SF truth remains one Route A, 39 places, 11 date keys, 3 regions, 93 timeline cards, and 24 legs. The canonical truth, route truth, photo integrity, and rights gates pass.

## Build and portability proof

The same builder was used for both package descriptors:

```text
python3 scripts/build_map_first.py --package packages/sf-family/trip.json --output-dir <temporary>/sf
python3 scripts/build_map_first.py --package packages/portability-fixture/trip.json --output-dir <temporary>/fixture
```

Canonical release qualification:

```text
python3 scripts/pipeline.py fast --revision 0fd8a4c52c53824ad1c304625ff2d70a87420ac5
python3 scripts/pipeline.py qualify --revision 0fd8a4c52c53824ad1c304625ff2d70a87420ac5
```

`QA/CHG-232/portability.json` is PASS. It records equal hashes for reusable renderer/build assets across the SF and Juniper fixture builds (`renderer_bytes_identical: true`, `renderer_source_unchanged: true`), no SF↔fixture leakage, and nonoverlapping route/date/region/place/provider/host identities. The fixture independently exercises COVE and RIDGE routes, 2041 dates, orchard/tideline regions, CNY, local photos, its own PMTiles identity/path, host policy, translations, and recovery content.

The ownership scan passes across the maintained builder, pipeline, manifest refresh, package loader, resilience/security QA, runtime, messages/state, shell, and CSS files. Its known forbidden SF-instance literals include the old canonical data path, SF PMTiles path/provider identity, Yosemite hillshade name, historical standalone filename, USD literal, current SF official hosts, and direct Esri/Google provider hosts. No matches were found in the scanned reusable files.

## Phone field evidence

`QA/CHG-232/phone_field_surface.json` is PASS, exact-bound to this candidate/tree. Both arrival-first-use and active route-day views are captured; route-day states contain 8 visible markers and 5 visible route features, retain the day itinerary, show at least 48 CSS pixels of next-item content, and have no horizontal overflow.

- [390×844 Korean/light route-day](screenshots/field_surface/sf-mobile-route-day-390x844-ko-light.png) — SHA-256 `75cafa74bfdd3d5053b001620ef1a5fc79311d58b5b9ed8edf5418868c254cfd`
- [320×800 English/dark route-day](screenshots/field_surface/sf-mobile-route-day-320x800-en-dark.png) — SHA-256 `1fc439d1605dbddc33b252c9e0e95109d696b7d067d288fa8d67e14f3853b7b0`
- [390×844 arrival first use](screenshots/field_surface/sf-mobile-390x844-ko-light.png)
- [390×844 place photos/context](screenshots/field_surface/sf-mobile-place-photos-390x844-ko-light.png)
- [1440×900 desktop route-day](screenshots/field_surface/sf-desktop-1440x900-ko-light.png)
- [390×844 portability-fixture surface](screenshots/field_surface/fixture-mobile-primary-390x844-en.png)
- [390×844 local-map recovery](screenshots/field_surface/sf-mobile-raster-failure-smart-recovery-390x844.png)

The phone report also checks the fixture's route/date/region filters, local photos, package-specific approved-source policy, denied arbitrary hosts/ports, provider failure recovery, and browser errors. These are objective automated measurements, not independent visual/usability acceptance.

## Qualification and performance

- `QA/CHG-232/release/fast.json`: PASS; reproducible build and authored inputs unchanged.
- `QA/CHG-232/release/qualification.json`: PASS; zero failures/errors, all automated components pass.
- `QA/CHG-232/gate5/candidate.json`: exact source binding PASS; performance comparison PASS; field-quality status is `VERIFY_REQUIRED` only for the external boundaries below.
- `QA/CHG-232/release/gate4_runtime.json`: PASS; single bounded raster failure and fallback, camera restored, task day/route context retained.

Paired Chromium performance, 8 samples per variant, versus baseline `7d5d8727b1772642e87311d91d087e211656f6e4`: median DOM content readiness improved 8.6 ms, Smart style readiness improved 13.3 ms, and first actionable state improved 39.8 ms. No sample was over 200 ms slower. Full samples and environment are in `QA/CHG-232/gate5/candidate.json`.

## Verification boundaries

- **VERIFY_REQUIRED:** native Safari automation is unavailable; Playwright WebKit is not native Safari.
- **VERIFY_REQUIRED:** no verifiably real iPhone or iPad was available.
- **VERIFY_REQUIRED:** independent candidate-bound multimodal visual/usability review has not been supplied. This implementation report makes no independent visual acceptance claim.
- The qualified Project OS Artifact Bridge is not exposed among the callable tools in this session, so the screenshot/report bundle could not be staged there. The exact-candidate local artifacts above are ready for that review.

No merge, deployment, Gate 5 closure, or production-readiness claim was made.
