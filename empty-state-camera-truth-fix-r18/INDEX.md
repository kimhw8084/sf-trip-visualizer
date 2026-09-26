# CHG-65 R18 empty-state camera truth repair

- Product candidate: `b260a0b4c38220f89af2e3b6772c46b5afc63c42` / tree `35fce613d2f1b01329b2dc502f82c22fdc628172`.
- Fresh base authority: `main` `fc195b1191fe4a430db0747b4264b8d036b6a48d`.
- Preserved predecessor: R16/R17 `6ea2619659ecc3b3cfb1f0797bebef70e0d55d96` / tree `37e979ac8514aff35612eea03a7919b655e846a8`; R17 made no Product source changes.
- R17 evidence lineage: Fabric `CF-9fee33200be3a3453eaa4cb3`, Artifact Run `AR-82`, carrier `7859a1e542b52a459e2259745a97876c620f0946`.
- Repair: an empty filtered spatial set now resolves camera context from existing `DATA.region_cfg` for the selected region (including `overall`), without adding markers, routes, or trip coordinates. Non-empty fits and camera retention through map reflow/options remain covered.
- EN map labels use the canonical existing region label when the translated region label is absent.
- Product data, route geometry, itinerary dates/stops and lodging policy were not changed.

## Exact-candidate qualification

- `python3 scripts/pipeline.py fast --revision b260a0b4c38220f89af2e3b6772c46b5afc63c42`: PASS.
- `python3 scripts/pipeline.py qualify --revision b260a0b4c38220f89af2e3b6772c46b5afc63c42`: PASS; Gate 5 status is `VERIFY_REQUIRED` with no reported failures.
- Focused `route_key_camera`: PASS across four mobile/touch viewports; includes region-then-date and date-then-region sequences, zero marker/route counts, DATA.region_cfg camera binding, no Yosemite place context, overall fallback, positive non-empty fit and Yosemite recovery with one canvas.
- Focused map geometry: PASS across 14 states. Focused visual suite: PASS, 50 screenshots. Direct-open standalone: positive PASS and negative control PASS (28 probes).

## Remaining Gate 5 verification boundaries

- native Safari remote automation is unavailable; Playwright WebKit is not a native Safari substitute
- no verifiably real iPhone or iPad is available in this execution environment
- independent candidate-bound multimodal visual/usability review is not supplied
- matched exact-main-versus-candidate performance remained directionally noisy after balanced repeated sampling

## No-results pixels

| State | Screenshot | Viewport | Language/theme | SHA-256 |
|---|---|---:|---|---|
| SF + 10/6 no-results (R17 region then date ordering; Yosemite 10/9 predecessor context) | [canonical_no_results_1440x900.png](images/canonical_no_results_1440x900.png) | 1440x900 | KO/light | `a5a2f47cfd80bb15ec42c507c3c1d362b8fa9385cea1fbb7bf263bb7555043b1` |
| SF + Marin 10/6 no-results (region then date) | [empty_state_sf_10-6_1440x900_ko_dark_region_then_date.png](images/empty_state_sf_10-6_1440x900_ko_dark_region_then_date.png) | 1440x900 | KO/dark | `8337694cfb7a068e80a365c188e5b0e66a00983e760c5a15bc80027a4020500d` |
| SF + Marin 10/6 no-results (date then region) | [empty_state_sf_10-6_1440x900_en_light_date_then_region.png](images/empty_state_sf_10-6_1440x900_en_light_date_then_region.png) | 1440x900 | EN/light | `f8341d6d83da4fd92023a470a5a666fde245a43779ed3c1278b5994b8459c049` |
| SF + Marin 10/6 no-results (date then region) | [empty_state_sf_10-6_1440x900_en_dark_date_then_region.png](images/empty_state_sf_10-6_1440x900_en_dark_date_then_region.png) | 1440x900 | EN/dark | `56759473d23c961f23368dc19104f7a9f1b8cd232162eda148d1dd896a1f9ab4` |
| SF + Marin 10/6 no-results (date then region) | [empty_state_sf_10-6_390x844_ko_light_date_then_region.png](images/empty_state_sf_10-6_390x844_ko_light_date_then_region.png) | 390x844 | KO/light | `848e4e64083d27d9b944893673e02d15738632a421295e2e58df3e573614abbe` |
| SF + Marin 10/6 no-results (region then date) | [empty_state_sf_10-6_390x844_ko_dark_region_then_date.png](images/empty_state_sf_10-6_390x844_ko_dark_region_then_date.png) | 390x844 | KO/dark | `31a95987b87afc68342cc2e11d97256a052a71f79b3c36fddf1a9bff39a4d9de` |
| SF + Marin 10/6 no-results (region then date) | [empty_state_sf_10-6_390x844_en_light_region_then_date.png](images/empty_state_sf_10-6_390x844_en_light_region_then_date.png) | 390x844 | EN/light | `971091807351ec4a9e3183595792381f5196c0a253313b8cd062ba3d3109e773` |
| SF + Marin 10/6 no-results (date then region) | [empty_state_sf_10-6_390x844_en_dark_date_then_region.png](images/empty_state_sf_10-6_390x844_en_dark_date_then_region.png) | 390x844 | EN/dark | `f1190e1be1211408b9fe2442f088d30e437ae2b394e814e35c0ec8b244593db8` |

Start with `reader_index.json`, `structured/qualification_summary.json`, and `structured/route_key_camera.json`. The complete canonical QA output remains in the Project worktree; this carrier contains the exact-candidate regression records and a small, representative pixel set. This evidence is published for review only; it has not been self-accepted or promoted. No integration or deployment was performed.
