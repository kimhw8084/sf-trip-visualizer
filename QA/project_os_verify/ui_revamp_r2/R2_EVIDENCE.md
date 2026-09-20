# CHG-157 R2 evidence

This pack is exact-candidate-bound. The stable source candidate is
`4a2520a8fb40ec789784fccf513de78f26318507` with tree
`1d42515d23cc6f1995e3ccc8f41da6802321dcf5`. The final evidence head is filled
after this evidence-only commit and is requalified separately.

## Lineage and source changes

- Fresh authoritative main: `f9631a57d3b9e51216e082b62d80519599b84711`, tree `11f886df2d0d9eb18f4550a399d533b10f7a4752`.
- R1 source reference: `819bb75f823f8a7bcdf6ef9902a958deba77b802`, tree `e750d5551b4e047a3f165eb19c4a1cea193d456c`.
- R1 generated evidence was not carried forward as current proof. The R2 pack was regenerated against the stable R2 source.
- Main → stable R2 source diff: 30 files, 2,286 insertions, 1,249 deletions.
- R1 source → stable R2 fix diff: 11 files, 1,147 insertions, 165 deletions.
- R1 → R2 source fixes: restored the hardened import-safe cross-browser runner and its isolated workers; added exact-clean-checkout evidence binding; added map obstacle measurement, dynamic safe padding and geometry oracle; added real Cook’s Meadow pointer activation; added Peek hover grace and Escape focus ownership; made the visual matrix and performance probe exact-bound and honest; and bounded `map_first_full` request classification for expected local PMTiles cancellations while retaining fail-closed unexpected-error checks.

The R1 Golden UI direction is preserved: Decide → Day → Place, human route recommendation/Compare, one Day date authority, Peek → Inspector, semantic tokens, mobile task sheet, immediate loading, local-first provider recovery and existing source-ownership boundaries.

## Marker occlusion repair

R1 reproduction: hosted run `35525724378`, job `106117411153`, failed `visual_spots`; Playwright’s first visible Cook’s Meadow marker was enabled and stable but the opaque `.map-chrome.map-top-left` intercepted pointer events for 30 seconds.

R2 repair is at the map geometry authority. The app measures the actual map chrome, MapLibre controls, workbench and persistent map surfaces, derives asymmetric camera padding, refits after geometry changes, and exposes `mapGeometrySnapshot()` for effective marker hit regions. It does not use forced clicks, JavaScript activation or pointer passthrough through opaque chrome.

The exact R2 geometry report covers 10 fitted states: desktop/mobile, overall and Yosemite, dense clustered and unclustered states, selected and unselected places, plus workbench/sheet variants. It reports PASS with zero marker/control intersections. Representative safe padding is desktop top/right/bottom/left `162/158/77/315` px and mobile `146/113/71/16` px. Cook’s Meadow is physically outside the top-left obstacle in desktop and mobile snapshots, and the cross-browser runner activates it with a real Playwright pointer click.

## Cross-browser qualification

The restored decisive contract has four rows: Firefox 1280×800 and 390×844 under hosted Linux + Xvfb + headful Firefox + software GL, and WebKit 1280×800 and 390×844 headless. It retains import-safe helpers, isolated worker processes, finite timeout/escalation, durable diagnostics before teardown, process-group cleanup, and fail-closed incomplete output handling.

Stable source hosted run `35531445349` / job `106132648968`: PASS. The hosted qualification JSON reports every component PASS, including cross-browser, map geometry, `map_first_full`, visual spots, Gate-4 runtime, public rights, canonical truth, photo integrity and security/privacy. Local exact-bound rerun also reports all four rows PASS, Cook’s Meadow activation PASS, three Inspector photos and zero geometry intersections.

## Task, accessibility and visual matrix

- `task_oracles.json`: 16/16 PASS, exact candidate/tree binding; recommendation/reason, two-route comparison, switch rule, Day required/optional/swap/recovery semantics, Peek → Inspector → return, Satellite failure recovery and real marker activation.
- `accessibility.json`: 6/6 PASS; visible focus, Escape/Back ownership, Day context preservation, 200% reflow, reduced motion and forced colors.
- `visual_index.json`: 32 real screenshots, each indexed with file, viewport, browser, language, theme, mode, state and task purpose. Canonical anchors: 1440×900 desktop and 390×844 mobile. Stress: 1366×768, 1920×1080, 360×800, 844×390 and 200% reflow. Fresh post-freeze holdouts: 1536×864 and 414×896; no new failure class recorded.
- Coverage includes Decide default/Compare, dense and sparse Day, no-results, Peek/Inspector, KO/EN, light/dark, loading, Smart failure, Satellite failure/recovery, desktop workbench compact/expanded/full, mobile compact/expanded/full, keyboard and touch paths.

## Performance

`performance.json` is a two-block order-balanced comparison with 8 samples per variant on the same Darwin/Chromium/1440×900 environment. It records distributions, paired deltas, DOM count, map layers, map visual readiness, workbench readiness and interaction response. DOM count falls from 1,757 baseline nodes to 439 candidate nodes. Because the legacy route-toggle interaction and R2 two-route Compare are not semantically identical tasks, the performance claim is intentionally `VERIFY_REQUIRED`; no performance PASS or FIX is asserted.

## Preservation and release-path results

- Canonical truth: 36 places, 108 photos, 79 timeline cards, 41 legs, 4 routes, 9 dates and 3 regions: PASS.
- Public rights, Gate-7 security/privacy/dependency/workflow checks, MapLibre security, Gate-4 runtime and standalone/public parity: PASS.
- MapLibre identity/hash preserved: `4.7.1+sf-trip-visualizer-r6`, SHA-256 `3e259a3d0e8d97c8e4d005cf21b86bba933818a80fe4b1fc4e402ff8c2318675`.
- `vendor/trip-vector.js` SHA-256 preserved: `fccb368f5ec3662547599238ca893761fa17f52ca25eb1875ad89db1ef51554d`.
- Current `src/app_phase7.js` hash binding: `56f409996fc202bf6f05a3905156d2409711ef8f60b1a75459e8e9e3e65a13b1`.
- Full unit suite: 46/46 PASS; `compileall`, JS syntax check and `git diff --check`: PASS.
- Hosted clean non-deploying release path for the exact stable source: `release --revision` PASS; `verify-public --revision` PASS. Public rights, security, MapLibre, Gate-4 parity and provenance binding all PASS. Production Pages was not deployed.

## Evidence boundary and classification

Fabric provides the exact source, objective geometry/task/accessibility evidence and hosted qualification. Native Safari, physical-device behavior and independent human/field review remain separate and are not represented as passed here. R1 historical reports remain history and are not current R2 proof.

Classification at stable source qualification: `VERIFY_REQUIRED` because the remaining performance comparison is intentionally semantically qualified and native/device/human evidence is outside this environment. Any final-head hosted failure would supersede this with `FIX_REQUIRED`.
