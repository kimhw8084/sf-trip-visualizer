# CHG-157 source architecture

The stable UI candidate keeps the static/local-first build and makes authored HTML own the product anatomy.

| Boundary | Owner | Responsibility |
|---|---|---|
| Authored shell | `src/map_shell_template.html` | App bar, persistent map, map controls, one Peek, one workbench, Decide/Day/Place views |
| State/persistence | `src/atlas_state.js` | Nested task/domain, presentation, runtime state; v2 local persistence and v1 migration |
| Critical copy | `src/atlas_messages.js` | Korean/English UI messages, decision labels, score labels, mode labels |
| Map adapter | `src/app_phase7.js` | MapLibre/PMTiles lifecycle, route layers, one marker per place, clustering, camera, provider failure |
| Decide renderer | `src/app_phase7.js` `renderDecide` | Recommended route, four strategy profiles, focused two-route comparison |
| Day renderer | `src/app_phase7.js` `renderDay` | Single date authority, temporal story, typed items, non-spatial plan cards, shared selection |
| Place renderer | `src/app_phase7.js` `renderPlace*` | Place browser, Peek → Inspector, authentic photo roles, timing, rules, directions, return context |
| Visual system | `src/app_phase7.css`, `src/map_first.css` | Semantic light/dark tokens, responsive shell, marker/route/map-only styles |
| Build boundary | `scripts/build_map_first.py` | Canonical data injection and deterministic modular/standalone assembly; no hidden interactive tree generation |
| QA instrumentation | `scripts/qa_decision_workbench.py`, `scripts/qa_accessibility_reflow.py`, maintained browser suites | Complete task/state oracles and rendered evidence |

The only workbench scroll owner is `.workbench-scroll`. Map panning/zooming is never the only discovery path: Day items, Place browser items, marker buttons, route hit layers, fit/recenter, and provider/region controls are all keyboard/pointer-operable.

Historical R11/R12 code was used only as evidence for proven resilience/accessibility mechanisms. No historical generated evidence is used as current proof.
