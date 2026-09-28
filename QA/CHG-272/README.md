# CHG-272 exact-revision evidence

Candidate `89b64e4db7ca1bb4dc600f136789e3ace21dd06c` is based directly on R3 head `101485bf0b66d33587b6dd7084da829456ae8dc2`. Candidate-bound reports and logs are indexed and SHA-256 hashed in `fabric_evidence.json`.

Native and hosted-style Linux qualification passed. Chromium/WebKit map geometry covered 320×800, 390×844, and 1440×900; Cook’s Meadow passed full-rectangle visibility, obstacle clearance, and real-pointer activation at 320×800. Gate4 standalone Ferry recovery passed with the marker inside the 320×800 map and real-pointer activation. Both native and Linux unit runs passed all 118 tests. Renderer bytes matched across the SF and Juniper fixture packages with empty cross-package leakage arrays.

Gate5 remains `VERIFY_REQUIRED` because this environment cannot provide native Safari, a verifiable iPhone/iPad, or an independent candidate-bound multimodal review. This is a review candidate; no GO decision or deployment was made. The hosted-style Pages release path assembled and verified local artifacts only.
