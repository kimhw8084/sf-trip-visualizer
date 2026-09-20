# CHG-157 R3 evidence handoff

Stable source: `bf200f781e7ebb080ddbece5df13950eb8e8e6a2`  
Stable tree: `0e0173c939c693f2e05dee52cfc40092e1e78fc6`  
Base main: `f9631a57d3b9e51216e082b62d80519599b84711`  
R2 source: `4a2520a8fb40ec789784fccf513de78f26318507` / tree `1d42515d23cc6f1995e3ccc8f41da6802321dcf5`

## Product repair

R3 replaces the persistent provider/region segmented block, separate fit/status chrome, and full route legend with one compact map-owned toolbar: current provider/region summary, Fit, adjacent material provider status, a single anchored Map Options disclosure, and a compact current-route key with on-demand explanatory legend. Route decision authority remains Decide-owned and date authority remains Day-owned. Options and legend close on Escape/outside action, restore focus to their explicit invokers, and are removed from the focusable surface while hidden. The open surfaces are measured transiently; their expanded geometry is not counted as persistent obstruction after close.

The geometry oracle records 18 states across desktop/mobile, options and route-key open/closed, regions, dates, selected/unselected Cook’s Meadow, and mobile sheet sizes. Against R2, default persistent opaque area falls about 58.7% desktop and 41.9% mobile; unobstructed interior rises from 89.82% to 95.80% desktop and 75.69% to 85.87% mobile. Marker/control hit testing is clean in the recorded states.

## Readiness repair

The exact R2 record is preserved in `performance.json` and `profiling_breakdown.json`: its matched record was 8/8 slower for `map_visual_ready` with approximately +498ms mean delta and DCL approximately +336ms. R3 marks canonical parse, authored evaluation, decision shell readiness, map runtime scripts, PMTiles, local style assets, MapLibre creation/style, route layers, photo preparation, markers, safe padding, fit, and final visual readiness.

Fresh order-balanced evidence has 8 samples per variant across two blocks. Current main vs R3: DCL mean `94.25ms` vs `38.47ms`; decision shell `286.93ms` vs `68.21ms`; map visual readiness `1063.66ms` vs `1057.33ms`. Map pair delta is mean `-6.33ms`, median `+14.46ms`, stdev `78.02ms`, 5/8 slower and 0/8 over 200ms. The performance component classifies `VERIFY_REQUIRED` for mild residual direction within observed noise; overall handoff remains `VERIFY_REQUIRED` pending hosted and independent external evidence.

## Automated evidence

- Task/state oracles: PASS, 19/19, including compact options/provider/region selection, Escape focus ownership, route-key disclosure, Cook’s Meadow pointer activation, Satellite recovery, and mobile sheet semantics.
- Accessibility/reflow: PASS, including visible focus, Escape, 200% reflow, reduced motion, and forced colors.
- Local browsers: PASS for Firefox and WebKit at 1280×800 and 390×844; open/closed option geometry and focus return included.
- Visual pack: 35 indexed real files covering canonical, compact options, region change, route key, provider failure, Decide/Day/Place, workbench sizes, stress profiles, and fresh 1536×864 / 414×896 holdouts.
- Repository checks: 46 unittest cases PASS; compileall, JavaScript syntax, and `git diff --check` PASS. Full local canonical qualification also passed all 19 components, including Gate-4 runtime resilience after it was updated to open Map Options before region selection.
- Hosted Linux qualification: PASS on post-freeze QA-only candidate `8d20be6fd926b7f5db97c9ad045d9f495dc79f1c` / tree `6e99993a1564b756dda763b2b1b1fd53b0f49f57`, run `35542814955`, job `106163431517`, artifact `10616015043`. All 19 decisive components, repository unit/contract checks, clean non-deploying Pages release, `verify-public`, and evidence upload passed under `ubuntu-latest`, Xvfb, software GL, and hosted-Linux Firefox mode. The earlier hosted 18/19 failure was isolated to an immediate QA focus assertion and is preserved as a diagnostic history, not a product failure.

R2→R3 complete diff: `r2_to_r3.diff` (including the Gate-6 rights-contract registration and changed first-party hashes). Preservation hashes and canonical counts are in `revision_manifest.json`. Fabric evidence is objective and does not self-certify aesthetic perfection.

## Qualification boundary

The next evidence-only commit must receive its own exact hosted rerun before final branch identity is closed; the preceding hosted candidate validation is durable in `qualification_hosted.json`. Native Safari, physical devices, independent human review, and Project OS Golden UI inspection remain external boundaries. Final classification: `VERIFY_REQUIRED`.
