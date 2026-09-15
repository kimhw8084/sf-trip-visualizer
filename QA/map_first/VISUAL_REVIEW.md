# Final visual review — 2026-09-14

Status: **PASS**

Inspected at original screenshot resolution:

- overall Smart map at 1440 px, with all routes and the panel visible;
- 10/8 Thursday at 1440 and 390 px, including the complete Valley–Glacier Point road loop;
- 10/4 Sunday at 1440 px, including the long recovery-gap connector;
- English dark mode with a selected place, hover preview, and three-photo detail panel;
- A1/A2/B1/B2 individually at 1440 and 390 px;
- responsive states at 1440, 1280, 1024, 768, 430, and 390 px;
- PIER 39 hover, Korean detail, English detail, and touch states;
- Firefox and WebKit at 1280 and 390 px;
- loading screen and standalone direct-open state.

Defects found and corrected during review:

- enlarged the fit-safe area so the on-map legend no longer covers the SF cluster;
- made informational overlays pointer-transparent;
- fitted non-transfer route geometry so mountain-road loops are not clipped and perceived as disconnected;
- removed zoom visibility cutoffs from every route layer;
- made route casings repeat the route’s dash pattern, eliminating white/gray ghost routes;
- increased colored route width and kept source route colors in both themes;
- expanded marker-label collision boxes to prevent stacked callouts;
- clamped route tooltips above the schedule ribbon;
- corrected QA capture waits so screenshots are taken only after vector tiles and the loading overlay settle.

Remaining intentional behavior: all four shared route lanes are visually dense when enabled together; toggling one strategy gives the cleanest turn-by-turn reading. Nearby stops cluster at low zoom and expand on click/tap. These are deliberate comparison and decluttering behaviors, not hidden data.
