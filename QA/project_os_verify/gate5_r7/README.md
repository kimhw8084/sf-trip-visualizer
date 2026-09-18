# Gate 5 R7 evidence index

Product candidate: `e9f6b752764a7e93c6f4308a2948e595af84cd30`.

The branch was reconstructed by fast-forwarding authoritative Fabric `main` at
`75d1f127dd5ce332df54e205e9a3d152de7af176` to the accepted candidate
`9c638f07d3942bbc10507f9e76d43aa4eb9ab621`, then applying the R7 product/test
commits. R6 verification-only commit `1ca3b4b3ae17c5fc31d44f125b448a90a9385413`
was not merged or reapplied. The final product SHA is the parent of this
evidence-only capture commit, if one is created.

## Root cause and correction

The preserved R4 candidate declared application readiness after MapLibre style
load plus a short animation boundary, while WebKit could still be completing
local sprite/font glyph work and a subsequent canvas render. Exact-candidate
probes showed `appReady=true` before the first MapLibre `idle` event at all
three representative WebKit sizes. The fix tracks every `tripasset://` sprite
and glyph PBF request and requires style loaded, tiles loaded, no map motion,
zero pending local resources, a post-resource MapLibre render, and two stable
animation frames before `mapVisualReady`/initial application readiness.

The fix does not suppress labels, replace the local Smart provider, rasterize
the map, or add a screenshot-only delay. When Smart is already active, failed
optional Satellite probing now preserves the existing ready Smart map instead
of rebuilding it; a real provider replacement still uses the semantic visual
readiness wait.

## Before / fixed visual evidence

- Exact R4 candidate WebKit objects from commit `9c638f0`: [`before_r4_exact_head`](before_r4_exact_head/)
- Exact-R4 readiness race probe: [`before_r4_9c638f0/probe.json`](before_r4_9c638f0/probe.json)
- Fixed final-candidate WebKit screenshots: [`fixed_e9f6b75`](fixed_e9f6b75/)
- Full final candidate browser report and source binding: [`gate5_candidate_e9f6b75.json`](qualification/gate5_candidate_e9f6b75.json)

The fixed capture covers WebKit 1440x900, 834x1112, and 390x844 in overall
and detail states. The Gate 5 matrix also captures the same states for
Chromium and Firefox, plus KO/light and EN/dark workflow states.

## Objective visual-integrity result

The map-only detector hides known UI controls, markers, route callouts, and
preview overlays before capture. It flags connected dark low-chroma components
only when area is at least 72 pixels, width at least 10, height at least 5,
and fill at least 0.42. Thresholds are calibrated from the clean same-browser,
same-viewport Gate-4 reference: clean component count + 2; total area at most
`max(180, clean_area*3+96)`; maximum component at most
`max(96, clean_max*1.75+48)`. These bounds preserve ordinary readable labels
while catching the widespread opaque rectangle class.

Final fixed WebKit map metrics, overall/detail:

| Viewport | Overall | Detail | Threshold basis |
|---|---:|---:|---|
| 1440x900 | 0 components / 0 px² | 0 / 0 px² | clean 7 components / 1047 px²; max 11 / 4248 px² |
| 834x1112 | 0 / 0 px² | 0 / 0 px² | clean 5 / 722 px²; max 7 / 2262 px² |
| 390x844 | 0 / 0 px² | 0 / 0 px² | clean 5 / 722 px²; max 7 / 2262 px² |

The regression test passes the clean Gate-4 baseline and fails a deterministic
fixture containing eight opaque low-chroma label rectangles:
[`test_map_visual_integrity.py`](metrics/test_map_visual_integrity.py).

## Qualification and hosted run

- Local fast qualification: `PASS` at `e9f6b75`.
- Full canonical qualification: all repository components `PASS`, including
  `map_first_full` with 600 states; Gate 5 remains `VERIFY_REQUIRED` only for
  independent E2 review, physical-device obligations, and non-decisive paired
  performance comparisons. See [`pipeline_qualification_e9f6b75.json`](qualification/pipeline_qualification_e9f6b75.json).
- Gate 5 source binding: exact clean commit `e9f6b75`, base exact clean commit
  `75d1f127...`; no decisive performance metric failed. See
  [`performance_summary_e9f6b75.log`](metrics/performance_summary_e9f6b75.log).
- Hosted exact-SHA run: GitHub Actions run `35355832528`, initially triggered
  from branch `codex/sf-trip-visualizer-field-ux-a11y-performance-g5-fix-r7`
  at head `e9f6b752764a7e93c6f4308a2948e595af84cd30`.
  URL: https://github.com/kimhw8084/sf-trip-visualizer/actions/runs/35355832528

## Separate VERIFY obligations

Project OS must independently adjudicate the fixed visual evidence/E2 result.
Real physical phone/device performance, memory, touch, and field-network
evidence remain outstanding. Public photo/third-party redistribution rights,
Gate 1 operator health proof, REC-179 final exact-main production baseline,
later gates, and final production certification remain separate.
