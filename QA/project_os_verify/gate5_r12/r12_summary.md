# CHG-65 R12 Gate-5 qualification-harness repair

Project: `sf-trip-visualizer`  
Authoritative main: `f9631a57d3b9e51216e082b62d80519599b84711`  
R11 stable source: `02f86c647395d61e7bd6ccdccb8e7883af981232` / tree `1668eb1ee325bdf80ad888c474254b117f6dbe16`  
R12 stable source candidate: `dcd92d1c01eeffd1603c14ee4d6c0135b7aa7bc1` / tree `36ec8d460b8445a9a32b26e7aee8a275dc3f8230`  
R12 final head: recorded after the QA/evidence-only commit containing this directory.

## Defect and repaired semantics

The R11 defect was execution/status conflation. Under the old path, Gate 5 exceeded the generic 300-second component bound, returned `124`, and left `status=UNVERIFIED`; the outer qualification nevertheless recorded `status=PASS` with `external_verify_required=[]` because Gate 5 was excluded from ordinary decisive failures unless its status was exactly `FAIL`.

R12 keeps `scripts/pipeline.py` as the only qualification/release authority and `scripts/qa_gate5_field_quality.py` as the only Gate-5 runner. The runner's process completion is now separate from its acceptance status:

- Gate 5 receives a dedicated finite `900` second bound. Ordinary components remain at `300` seconds.
- Before invocation, the expected report is removed. The canonical authority records the invocation marker and requires a fresh report.
- A nonzero return code, timeout/`124`, missing report, stale report, malformed report, wrong candidate head/source binding, or `UNVERIFIED` execution result is canonical `FAIL` and is never an external verification boundary.
- Only `rc=0` plus a fresh clean exact-commit report with terminal `PASS` or explicit `VERIFY_REQUIRED` is accepted as completed execution.
- Completed Gate 5 `VERIFY_REQUIRED` remains an accepted non-production qualification outcome only when `external_verify_required` includes `gate5_field_quality`.
- Release mode consumes that same qualification report and cannot assemble public output after a Gate-5 execution failure.

The 900-second budget is finite and justified by the complete browser/accessibility matrix, same-host WebKit control, and two order-balanced eight-sample performance blocks. R11 exceeded 300 seconds; fresh R12 complete runs took 191.738 seconds directly, 311.134 seconds in hosted candidate qualification, and 311.304 seconds in the clean release path, leaving at least 588 seconds of headroom in the hosted runs. No global timeout was relaxed.

The deterministic matrix is in `status_matrix.json`; the executable regression is `tests/test_gate5_qualification.py`.

## Source reconstruction and preservation

R11 final head `34fd3e25fd122c1627e327a2f4372ea66f8bd352` was not integrated and its generated evidence was not used as R12 proof. R12 was reconstructed from the R11 stable source candidate, then only the following seven source/test files changed relative to R11 stable:

```
M .github/workflows/candidate-qualification.yml
M manifests/canonical_pipeline.json
M manifests/gate5_field_quality_contract.json
M scripts/pipeline.py
M scripts/qa_gate5_field_quality.py
M tests/test_canonical_pipeline.py
A tests/test_gate5_qualification.py
```

Relative to fresh authoritative main, the candidate also carries the reconciled R11 product and QA lineage. The exact `git diff --name-status` set is:

```
M .github/workflows/candidate-qualification.yml
M manifests/canonical_pipeline.json
A manifests/gate5_field_quality_contract.json
M manifests/public_asset_rights.json
M scripts/build_map_first.py
M scripts/pipeline.py
M scripts/qa_gate4_resilience.py
A scripts/qa_gate5_field_quality.py
M scripts/qa_interaction_dynamics.py
A scripts/qa_loading.py
A scripts/qa_location_gap_race.py
M scripts/qa_location_gap_visuals.py
M scripts/qa_map_first_full.py
A scripts/qa_map_visual_integrity.py
M scripts/qa_route_explanations_panel.py
M scripts/qa_standalone_map_first.py
M scripts/run_cross_browser.py
M scripts/run_visual_spots.py
M src/app_phase7.js
M src/map_first.css
M src/map_shell_template.html
M tests/test_canonical_pipeline.py
A tests/test_gate5_performance_evidence.py
A tests/test_gate5_qualification.py
A tests/test_loading_completion.py
A tests/test_location_gap_race.py
A tests/test_map_visual_integrity.py
```

The product/runtime/rendering files and required security/release inputs are byte-identical between R11 stable and R12. The exact SHA-256 record is `preservation_hashes.json`; it includes the required MapLibre digest `3e259a3d0e8d97c8e4d005cf21b86bba933818a80fe4b1fc4e402ff8c2318675` and derivative `4.7.1+sf-trip-visualizer-r6`.

## Direct Gate-5 execution

The runner was invoked directly on the exact source candidate and completed normally:

```
status=VERIFY_REQUIRED
returncode=0
duration_seconds=191.738
candidate_head=dcd92d1c01eeffd1603c14ee4d6c0135b7aa7bc1
candidate_tree=36ec8d460b8445a9a32b26e7aee8a275dc3f8230
source_binding.status=PASS
source_worktree_dirty=false
failures=[]
```

The explicit unresolved boundaries are E2 independent multimodal visual/usability acceptance, native Safari on macOS preflight/evidence, real physical iPhone/iPad field evidence and memory claim, and same-environment performance comparison because the comparison is not evidence-complete. No native Safari or physical-device evidence was fabricated or substituted.

## Hosted candidate and clean release path

Hosted run: [35512960890](https://github.com/kimhw8084/sf-trip-visualizer/actions/runs/35512960890)  
Successful rerun job: `106087859446`  
Successful rerun artifact: `10606383485`, `candidate-qualification-dcd92d1c01eeffd1603c14ee4d6c0135b7aa7bc1`, 71,623,881 bytes. Selected reports are preserved under `hosted_run_35512960890/`.

The hosted job checked out the exact triggering SHA, installed hash-pinned QA dependencies and Chromium/Firefox/WebKit, ran full qualification, ran repository tests, checked out a clean exact revision, exercised `scripts/hosted_linux_pipeline.py release --revision <candidate>` followed by `scripts/pipeline.py verify-public --revision <candidate>`, and uploaded evidence. No deployment occurred.

Both durable hosted qualification reports agree:

| Path | Outer status | Gate-5 status | rc | timeout | process completed | execution status | external_verify_required |
|---|---|---|---:|---:|---|---|---|
| `hosted_run_35512960890/candidate/qualification.json` | PASS | VERIFY_REQUIRED | 0 | 900 | true | COMPLETED | `gate5_field_quality` |
| `hosted_run_35512960890/release_path/qualification.json` | PASS | VERIFY_REQUIRED | 0 | 900 | true | COMPLETED | `gate5_field_quality` |

Candidate Gate-5 duration was 311.134 seconds; release-path Gate-5 duration was 311.304 seconds. Both reports bind the exact candidate head and tree, report a clean worktree, have empty failures, and have performance status `VERIFY_REQUIRED` rather than claiming stable non-regression.

The first hosted attempt on this same source had a one-metric `warm_milestones.smart_style_ready` performance comparator failure in the clean release exercise after the candidate qualification had passed. That historical attempt is retained only as variance context; the successful rerun completed the clean release path with the documented performance boundary unresolved. It is not used as current R12 proof.

## Verification results

- Focused Gate-5 and canonical pipeline tests: passed, 16 tests.
- Full repository unittest discovery: passed, 78 tests.
- Python syntax compilation and `git diff --check`: passed.
- `scripts/pipeline.py fast --revision dcd92d1c01eeffd1603c14ee4d6c0135b7aa7bc1`: passed.
- MapLibre security check: passed.
- Gate-7 security/privacy, workflow trust, dependency artifact coverage, and hash-pinned dependency checks: passed.
- Gate-6 public-asset rights checks: passed in the candidate fast/release qualification and hosted release path.
- Gate-4 static resilience/offline/provider-recovery checks: passed; hosted browser qualification also passed.
- Local hosted-Linux execution was unavailable because `xvfb-run` is not installed; the required shared hosted-Linux contract was completed by the hosted run above.

The remote work branch equals the final head after the evidence-only commit, the worktree is clean, authoritative main remains unchanged, and the base ancestry check from `f9631a57d3b9e51216e082b62d80519599b84711` is true. No merge, deployment, REC-179 resolution, Gate 8 work, or production-readiness claim was made.

## Classification

`VERIFY_REQUIRED`: the deterministic Gate-5 execution/status and release-harness defect is fixed; automated qualification and the clean non-deploying release path complete correctly; native Safari, physical-device, independent E2 visual/usability, and variance-limited performance evidence remain explicit external boundaries. This is not `GO_READY_EVIDENCE`.
