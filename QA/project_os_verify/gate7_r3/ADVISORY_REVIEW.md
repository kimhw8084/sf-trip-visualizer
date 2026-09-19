# Current advisory review — exact recovered components

Review date: `2026-09-19`.

The isolated exact JS workspace ran `npm audit --json`: 64 dependencies, 0 info, 0 low, 0 moderate, 0 high, 0 critical.

| Component | Current authoritative review | Exact-version result | Exposure |
|---|---|---|---|
| `fflate 0.8.3` | [GHSA-px8p-9vwx-vf98 / CVE-2026-45820](https://github.com/advisories/GHSA-px8p-9vwx-vf98), affected `<0.8.3`, patched `0.8.3` | PASS at patched boundary | Embedded in shipped trip-vector bundle |
| `pmtiles 4.5.0` | [PMTiles security advisories](https://github.com/protomaps/PMTiles/security/advisories); no maintainer advisory found; npm audit zero | No hit in reviewed sources; not a universal clean-bill claim | Embedded in shipped trip-vector bundle |
| `@protomaps/basemaps 5.7.2` | [Basemaps security](https://github.com/protomaps/basemaps/security); no maintainer advisory found; npm audit zero | No hit in reviewed sources; not a universal clean-bill claim | Embedded in shipped trip-vector bundle |
| `esbuild 0.28.2` | [esbuild advisories](https://github.com/evanw/esbuild/security/advisories): `GHSA-gv7w-rqvm-qjhr`, `GHSA-g7r4-m6w7-qqqr`, `GHSA-67mh-4wv8-2f99` | Exact version outside affected ranges | Build-time only; not shipped |
| `playwright 1.62.0` | [GHSA-7mvr-c777-76hp / CVE-2025-59288](https://github.com/advisories/GHSA-7mvr-c777-76hp), affected `<1.55.1`, patched `>=1.55.1` | PASS; exact version outside affected range | QA/browser automation only |
| Firefox `153.0`, revision `1538` | [Mozilla MFSA-2026-74](https://www.mozilla.org/en-US/security/advisories/mfsa2026-74/), `CVE-2026-74990`, fixed in `153.1/154` | QA-only advisory note; not shipped runtime | Playwright QA browser cache only |

Playwright and Playwright-Python maintainer advisory pages were also checked and had no published advisories at review time. No exact Chromium `151.0.7922.34` advisory was identified in the authoritative sources reviewed, and no universal clean claim is made. The Apple Safari 26.5 advisory surface was not treated as an exact Playwright WebKit-build match.

The Firefox finding does not trigger shipped-runtime `FIX_REQUIRED`: the product ships the recovered JavaScript bundle, not the Playwright browser archives. If a separate organizational policy treats QA browsers as deployed runtime, that policy boundary requires an independent decision; this evidence-only task does not alter the pinned package or browsers.
