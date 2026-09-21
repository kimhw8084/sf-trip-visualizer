# CHG-157 R4 evidence handoff

This is the durable R4 evidence index for the bounded mobile compact-sheet repair. R1–R3 evidence remains immutable under its original directories. Fabric does not self-certify aesthetic perfection; Project OS must independently inspect the captured pixels.

## Exact source boundary

| item | exact identity |
|---|---|
| authoritative target/main | `f9631a57d3b9e51216e082b62d80519599b84711` / tree `11f886df2d0d9eb18f4550a399d533b10f7a4752` |
| reconstructed R3 stable source | `bf200f781e7ebb080ddbece5df13950eb8e8e6a2` / tree `0e0173c939c693f2e05dee52cfc40092e1e78fc6` |
| stable R4 source candidate | `bd65a4400cca6f7a48c4ce124a687498ea0e035b` / tree `8d65423268222a9fa0fffe00784825d6171a21e5` |
| stable R4 source parent | `f9631a57d3b9e51216e082b62d80519599b84711` |
| R3 Fabric receipt | `CF-df62f1bb2451e02d3a1af853` |
| R3 final work head | `5d9604f96ccf7d0cf5bb3872c219692aad56cf11` |
| R3 hosted qualification | run `35543706582`, job `106165804140` |

The complete R3→R4 source diff is [r3_to_r4_source.diff](./r3_to_r4_source.diff): 12 files, 385 insertions and 41 deletions. It excludes generated R3 evidence. No current R4 acceptance report binds `WORKTREE`; all decisive JSON reports bind the stable SHA/tree above.

After the stable source freeze, only generated evidence is eligible for the final evidence-head commit. The final managed-branch SHA/tree is intentionally not copied into this manifest/report as a self-referential claim; remote branch identity, Fabric audit and Project OS postflight are final-head authority.

## Bounded repair

- Mobile compact now changes the outer `.workspace` geometry to `minmax(0, 1fr) max-content`; expanded retains the 56%/44% split; full retains task-dominant full-workspace geometry.
- One semantic workbench remains authoritative. Mode, route/date/place, provider, language/theme, selected place, focus context and explicit sheet state are preserved through transitions and orientation recomposition.
- Compact exposes its head/mode context and visible expand/full controls. Hidden scroll content is `hidden`, `inert`, `aria-hidden` and has zero visible focusables.
- MapLibre resize/refit is coalesced through one animation-frame scheduler and a `ResizeObserver`; readiness remains tied to `mapVisualReady` after style/load, marker installation and fit.
- Safe padding preserves the overlay side’s clearance while clamping the opposing side to a valid budget. This fixed the real narrow-mobile NaN/invalid-LngLat path and preserved marker reachability with Map Options and route-key overlays open.

## Mobile sheet geometry oracle

Rendered DOM geometry from `sheet_geometry.json`; all six viewports and 40 transitions passed.

| viewport | sheet | map height | workbench height | useful-map ratio |
|---|---:|---:|---:|---:|
| 360×800 | compact | 648.00 | 101.00 | 0.8951 |
| 360×800 | expanded | 419.44 | 329.55 | 0.8379 |
| 360×800 | full | 749.00 | 749.00 | 0.0000 |
| 390×844 | compact | 692.00 | 101.00 | 0.9093 |
| 390×844 | expanded | 444.08 | 348.91 | 0.8587 |
| 390×844 | full | 793.00 | 793.00 | 0.0000 |
| 414×896 | compact | 744.00 | 101.00 | 0.9193 |
| 414×896 | expanded | 473.19 | 371.80 | 0.8731 |
| 414×896 | full | 845.00 | 845.00 | 0.0000 |
| 844×390 landscape | expanded | 308.72 | 308.72 | 0.7974 |
| 844×390 landscape | full | 308.72 | 308.72 | 0.7974 |
| 844×390 landscape | compact | 308.72 | 0.00 | 0.8906 |
| 375×812 holdout | compact | 660.00 | 101.00 | 0.9011 |
| 375×812 holdout | expanded | 426.16 | 334.83 | 0.8469 |
| 375×812 holdout | full | 761.00 | 761.00 | 0.0000 |
| 1600×900 holdout | expanded | 812.13 | 812.13 | 0.9622 |
| 1600×900 holdout | full | 812.13 | 812.13 | 0.9622 |
| 1600×900 holdout | compact | 812.13 | 0.00 | 0.9781 |

Compact is materially larger than expanded on every portrait profile. Landscape/desktop retain the explicit state while adapting presentation: compact becomes a desktop collapsed workbench with the appbar toggle as predictable focus target; returning to mobile restores the bottom-sheet compact presentation without resetting task state.

## State, focus and task results

- `sheet_geometry.json`: PASS; pointer, keyboard and touch transitions compact→expanded→full→expanded→compact; task signatures remained stable; transition timing min 114.64ms, mean 363.71ms, max 1081.70ms.
- `task_oracles.json`: PASS, 19/19. Recommendation/reason, two-route comparison, Day authority, Peek→Inspector→return, Satellite recovery, compact provider/region options, route-key disclosure and real Cook’s Meadow pointer activation all passed.
- `accessibility.json`: PASS, 6/6. Visible focus, Escape ownership/context, 200% reflow, reduced motion and forced colors passed.
- Compact hidden-content proof: `scroll_hidden=true`, `scroll_inert=true`, `scroll_visible_focusables=0` in every compact transition row.
- Escape priority remained map options → route key → Peek → Place → full-sheet collapse; compact/expanded is not changed unexpectedly.

## Performance

`performance.json` is the balanced 8-sample/two-block 1440×900 Chromium probe using current main, actual recorded R2 source and R4. The retained R4 replay reports:

| milestone | current main mean | R4 mean | R4−main |
|---|---:|---:|---:|
| DOM/content ready | 85.38ms | 36.40ms | −48.98ms |
| decision workbench ready | 266.07ms | 68.44ms | −197.63ms |
| `map_visual_ready` | 1042.53ms | 1002.92ms | −39.61ms |

The probe classified PASS (map slower 3/8 pairs, no map sample >200ms). `performance_replay_audit.json` records an earlier non-reproducible +348.19ms outlier and the restarted-server replay used for the retained report. R3’s accepted comparison remains approximately current-main 1063.66ms vs R3 1057.33ms; the R2 +498ms/8-of-8 pattern is not reproduced.

## Visual/browser evidence

- `visual_index.json`: PASS, 48 Chromium screenshots, including canonical 1440×900, 390×844, mobile compact/expanded/full at 360×800, 390×844, 414×896, fresh 375×812, landscape, 1600×900 desktop holdout, compact map options/route key, English/dark, Place context, provider failure/recovery and keyboard/touch Peek.
- `browser_summary.json`: PASS, isolated Firefox and WebKit at 1280×800 and 390×844; zero page/console/request/map errors, no horizontal overflow, 36 markers and real Cook’s Meadow activation.
- `map_geometry.json`: PASS, 18/18 states; map options/route-key safe areas, marker hit regions, Cook’s Meadow pointer activation and compact/expanded geometry all passed.

## Full qualification and preservation

- Local `pipeline.py fast`: PASS on stable source.
- Local `pipeline.py qualify`: PASS; canonical truth, photo integrity, public rights, MapLibre security, Gate-7 checks, Gate-4 runtime resilience, standalone/public parity, route continuity, exhaustive states, map geometry, cross-browser and visual spots all passed.
- Repository unit discovery: 46/46 PASS; compileall, JavaScript syntax and `git diff --check` PASS.
- Canonical counts preserved: 36 places, 108 photos, 79 timeline cards, 41 route legs, four routes, nine dates, three regions.
- Vendor hashes preserved: `vendor/maplibre-gl.js` SHA-256 `3e259a3d0e8d97c8e4d005cf21b86bba933818a80fe4b1fc4e402ff8c2318675`; `vendor/trip-vector.js` SHA-256 `fccb368f5ec3662547599238ca893761fa17f52ca25eb1875ad89db1ef51554d`.
- Hosted stable-source qualification: PASS, run `35557938769`, job `106205142325`, exact SHA `bd65a4400cca6f7a48c4ce124a687498ea0e035b`; artifact `candidate-qualification-bd65a4400cca6f7a48c4ce124a687498ea0e035b`, artifact ID `10621331580`. The exact clean non-deploying Pages release and `verify-public` both passed; public staging artifact SHA-256 was `92d46eb5b97b9e326afe1dddf0063ceef2f7c9266eb61a5b7844521676a22eb4` (248 files).

## Boundaries and classification

No merge, deployment, Gate 5 closure, REC-179 resolution, Gate 8 completion or production-readiness claim is made. Native Safari, physical-device behavior, independent human/field review, Project OS pixel review and truly noise-bound performance questions remain external.

Classification: `VERIFY_REQUIRED`. The exact source, automated evidence, hosted qualification, clean non-deploying release and `verify-public` are green. Native Safari, physical-device behavior, independent human/field review and Project OS pixel postflight remain external, so `GO_READY_EVIDENCE` is not claimed.
