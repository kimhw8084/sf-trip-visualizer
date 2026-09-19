# Gate 5 / CHG-65 R10 verification record

Project: `sf-trip-visualizer`  
Recorded: 2026-09-19T00:51:16Z  
Scope: evidence-only continuation of independently audited R9. This record does not claim Gate 5 GO, integration, production readiness, or release.

## Exact bindings

| Binding | Value |
| --- | --- |
| Managed R10 verification branch | `codex/sf-trip-visualizer-field-ux-a11y-performance-g5-verify-r10` |
| Authoritative transport base/main | `75d1f127dd5ce332df54e205e9a3d152de7af176` |
| Immutable R9 Fabric capture | `9545401f2dad58d932b5de7f19c8f121ac024d9d` |
| R9 source/runtime revision | `f9edf2021451cc3040407636c226897a4505a8b7` |
| Gate-4 comparison checkout | detached `75d1f127dd5ce332df54e205e9a3d152de7af176` |
| R9 candidate checkout | detached `9545401f2dad58d932b5de7f19c8f121ac024d9d` |
| Gate 5 contract Git blob | `a95a6fbb9e5b8b998319eed5655ce9e3cf4821cb` |
| R9 source fingerprint | `3b76e5c630b718433d60e9e23c6846433964e2b23f5b15bb5a74a25860ccd831` (`340` files; generated QA/build/release/public-site excluded) |

Both detached checkouts were clean and exact-SHA verified. The managed R10 branch was clean before evidence preparation and remained based on authoritative base.

## Safari-on-macOS execution result

**`VERIFY_REQUIRED` — genuine Safari execution was not possible in this environment.**

Safari is installed and the driver is reachable, but Safari itself refused the WebDriver session because `Allow remote automation` is disabled in Safari Settings → Developer. `safaridriver --enable` requested an administrator password and did not enable the setting. The CUA connector also could not attach to a Safari window (`cgWindowNotFound`). No Safari candidate or base page was therefore exercised, and no Safari screenshots or Safari runtime observations are claimed.

Exact host/runtime identity:

- macOS 26.6.2, build `25G83`; Darwin kernel `25.6.0`; arm64 Mac15,7, Apple M3 Pro.
- Safari bundle `com.apple.Safari`, version `26.6.2`, build `21624.5.1.11.3`, path `/Applications/Safari.app`.
- `safaridriver --version`: `Included with Safari 26.6.2 (21624.5.1.11.3)`.
- Driver `/status`: ready.
- Session creation response: `session not created — You must enable 'Allow remote automation' in the Developer section of Safari Settings to control Safari via WebDriver.`

Because no native Safari session was created, the requested candidate-bound desktop, narrow, and mobile-sized responsive states; map readability and label/glyph rendering; overall/detail; route/date/region/provider; Korean/English; light/dark; keyboard/focus; provider recovery; overflow/occlusion; and critical runtime-error checks are all **unperformed Safari checks**, not passes or fails. Playwright WebKit is not relabeled as Safari evidence.

## Physical-device result

**`VERIFY_REQUIRED` — no physical iPhone or iPad was attached and verifiably usable.** `xcrun xctrace list devices` reported only this Mac plus iPhone/iPad simulators; `xcrun devicectl list devices` reported only a shutdown simulated iPhone 17 Pro; `SPUSBDataType` reported no attached device; no `idevice_id` bridge was available. Simulator output was not used as hardware evidence. No real-device first-use, interaction, OS, browser, or performance claim is made.

## Carried exact R9 facts and comparison interpretation

These facts are preserved from the immutable R9 evidence and are not relabeled as native Safari:

- Canonical map-first full acceptance: `PASS` (`QA/map_first/full_acceptance.json`, Git blob `be73e6a78ee4799143a57753b4ac8d3d381d2df6`).
- Location-gap race/visual evidence: `PASS` (`QA/map_first/location_gap_visuals.json`, Git blob `94f3df37c194b3bbc07963773f603c6253e227d3`).
- Gate 5 finding matrix: 14 rows, 10 `PASS`, 4 `VERIFY_REQUIRED`, zero `FAIL` (`QA/gate5/finding_matrix.json`, Git blob `572478eec3c2db223213c3343f69a437850bc29f`).
- Automated Chromium, Firefox, and Playwright WebKit rows at 1440/834/390: all nine rows `PASS` in R9 candidate evidence (`QA/gate5/candidate.json`, Git blob `4c427ac972522c433c9002e12cd669188ec44f7c`). These are automated browser/emulation rows, not Safari or physical-device evidence.
- Same-host Gate-4-versus-R9 Playwright WebKit controls: each 1440x900, 834x1112, and 390x844 overall/detail detector was `PASS` and within the base envelope (`QA/gate5/same_host_webkit_control.json`, Git blob `6ad69937086d7106e5e4588e8749f1be350629e8`). The aggregate decision remains `VERIFY_REQUIRED` pending representative Safari/macOS adjudication.
- R9 performance: no decisive regression; paired measurements are noisy/inconclusive. The exact paired evidence remains `VERIFY_REQUIRED` under the existing performance law (`QA/gate5/paired_comparison.json`, Git blob `c287d82da11481ed4b837bf014b7eeff850b07ba`; summary log Git blob `2092664ce3c3ba06102a49b6707fef2b0c7b8517`). No detector or performance law was weakened.

The available evidence established no concrete candidate/source defect, so no `FIX_REQUIRED` was recorded. It also cannot rule out a Safari-specific defect because the native Safari session was blocked.

## Remaining `VERIFY_REQUIRED` requirements

1. Enable Safari remote automation on this Mac, then repeat the exact candidate and exact Gate-4 base in genuine Safari/safaridriver with deterministic screenshots and structured observations across the requested desktop, narrow, and mobile-sized states. State that responsive viewport sizing is not iPhone/iPad hardware evidence.
2. Obtain independent, candidate-bound E2 multimodal visual/usability acceptance. This implementation/verification agent does not self-certify that layer.
3. If real hardware is required, attach and verify a physical iPhone or iPad and record exact device, OS, and browser identity, including first-use readiness and representative core interactions.
4. Preserve the existing performance conclusion until a fresh exact, instrumented comparison is independently justified; current paired timing evidence remains noisy/inconclusive.

