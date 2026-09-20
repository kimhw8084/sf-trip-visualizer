# CHG-157 R3 evidence handoff

Stable source: `2fa5dd1acc63f49230f772bd5ce39cd733331c0b`  
Stable tree: `3f08ed4c850f989a7481d33aeceb09bd76c51f35`  
Base main: `f9631a57d3b9e51216e082b62d80519599b84711`  
R2 source: `4a2520a8fb40ec789784fccf513de78f26318507` / tree `1d42515d23cc6f1995e3ccc8f41da6802321dcf5`

## Product repair

R3 replaces the persistent provider/region segmented block, separate fit/status chrome, and full route legend with one compact map-owned toolbar: current provider/region summary, Fit, adjacent material provider status, a single anchored Map Options disclosure, and a compact current-route key with on-demand explanatory legend. Route decision authority remains Decide-owned and date authority remains Day-owned. Options and legend close on Escape/outside action, restore focus to their explicit invokers, and are removed from the focusable surface while hidden. The open surfaces are measured transiently; their expanded geometry is not counted as persistent obstruction after close.

The geometry oracle records 18 states across desktop/mobile, options and route-key open/closed, regions, dates, selected/unselected Cook’s Meadow, and mobile sheet sizes. Against R2, default persistent opaque area falls about 58.7% desktop and 41.9% mobile; unobstructed interior rises from 89.82% to 95.80% desktop and 75.69% to 85.87% mobile. Marker/control hit testing is clean in the recorded states.

## Readiness repair

The exact R2 record is preserved in `performance.json` and `profiling_breakdown.json`: its matched record was 8/8 slower for `map_visual_ready` with approximately +498ms mean delta and DCL approximately +336ms. R3 marks canonical parse, authored evaluation, decision shell readiness, map runtime scripts, PMTiles, local style assets, MapLibre creation/style, route layers, photo preparation, markers, safe padding, fit, and final visual readiness.

Fresh order-balanced evidence has 8 samples per variant across two blocks. Current main vs R3: DCL mean `94.94ms` vs `38.66ms`; decision shell `287.90ms` vs `74.71ms`; map visual readiness `1065.68ms` vs `1061.86ms`. Map pair delta is mean `-3.83ms`, median `+15.75ms`, stdev `93.25ms`, 6/8 mildly slower and 0/8 over 200ms. Classification remains `VERIFY_REQUIRED` because this is residual direction within observed noise, not a fabricated hard budget.

## Automated evidence

- Task/state oracles: PASS, 19/19, including compact options/provider/region selection, Escape focus ownership, route-key disclosure, Cook’s Meadow pointer activation, Satellite recovery, and mobile sheet semantics.
- Accessibility/reflow: PASS, including visible focus, Escape, 200% reflow, reduced motion, and forced colors.
- Local browsers: PASS for Firefox and WebKit at 1280×800 and 390×844; open/closed option geometry and focus return included.
- Visual pack: 35 indexed real files covering canonical, compact options, region change, route key, provider failure, Decide/Day/Place, workbench sizes, stress profiles, and fresh 1536×864 / 414×896 holdouts.
- Repository checks: 46 unittest cases PASS; compileall, JavaScript syntax, and `git diff --check` PASS.

R2→R3 complete diff: `r2_to_r3.diff`. Preservation hashes and canonical counts are in `revision_manifest.json`. Fabric evidence is objective and does not self-certify aesthetic perfection.

## Qualification boundary

At handoff, hosted-Linux Firefox/Xvfb qualification, exact managed-branch equality, hosted clean Pages release-path exercise, `verify-public`, and evidence-upload identities remain to be established. Native Safari, physical devices, independent human review, and Project OS Golden UI inspection remain external boundaries. Final classification: `VERIFY_REQUIRED`.
