# Deterministic bundle reproduction

Historical source commit: `3455a3ec339f434d840551f425ee7b68a690377f`  
Historical source tree: `0f68fae6835340083dbe9f0cb4af7383c12f750b`  
Entrypoint: `src/vector_entry.js`  
Target: `vendor/trip-vector.js`  
Target SHA-256: `fccb368f5ec3662547599238ca893761fa17f52ca25eb1875ad89db1ef51554d`

The historical tree has no tracked JS lockfile, manifest, dependency workspace, or bundler configuration. Recovery was performed in a temporary directory outside the repository. The entrypoint was copied from the detached historical checkout. The following exact package tarballs were installed from the npm registry using their recorded npm integrity values:

```text
fflate@0.8.3
pmtiles@4.5.0
@protomaps/basemaps@5.7.2
esbuild@0.28.2
```

The deterministic command was:

```text
.tools/jsdeps/node_modules/.bin/esbuild src/vector_entry.js --bundle --format=iife --outfile=vendor/trip-vector-cli.js
```

Observed result:

```text
vendor/trip-vector-cli.js  72.2kb
Done in 28ms
sha256: fccb368f5ec3662547599238ca893761fa17f52ca25eb1875ad89db1ef51554d
cmp generated historical: exit 0
cmp generated candidate: exit 0
```

The no-minify option is material. A `minify=true` control generated 57,217 bytes, 15 lines, and SHA-256 `de33478707ee64eae78522a222264c7c5f52fcf799d0ba5efca75bad1b0882b7`, which did not match.

Registry and source identities are recorded in `evidence.json`; the decisive proof is the exact byte comparison, not API resemblance or module similarity.
