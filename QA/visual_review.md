# Visual QA — final v2 candidate

Inspected the actual browser screenshots, not just DOM assertions: overall and SF/Monterey/Yosemite at 1440 px; all four individual route colors at 1440 and 390 px; the A1 + 10/9 + Yosemite edge case; Ferry/Mariposa details; 1440/1280/1024/768/430/390 responsive views; 390/430 tap previews and detail panels; live USGS, OSM, and Esri; Firefox and WebKit desktop/mobile details; and the expanded mobile route guide. Source images and the 28 hero thumbnails were inspected via the photo contact sheets.

Corrections made after inspection:

- Replaced the blank/minimalist offline backdrop with four locally bundled, georeferenced USGS topo mosaics. The live "Light" slot is now accurately named USGS Topo; the unusable CARTO key-watermarked tiles are no longer offered.
- Removed dark Plotly-style route dots and the four-striped common-leg overlay. Shared legs now have one neutral dashed connector; a single selected route uses its actual blue/green/red/purple color. The route pills retain those colors in light mode.
- Constrained connectors to regional zoom and hid them at stop-detail zoom so close-up photographs and geography are not crossed by long schematic strokes.
- Fitted filtered stops into the viewport with mobile-aware padding. Stopped zooming bundled imagery beyond native detail when focusing a place; Yosemite/Monterey use zoom 11 and SF uses zoom 12.
- Expanded the right-side timeline with route/shared status, mapped-stop identity, timing rationale, and advantage. The detail panel now shows an immediate time/status/why/advantage brief above a large hero and two supporting photographs, followed by all exact deduplicated timings and decision rules.
- Reduced mobile map height to 52% of the workspace to give the itinerary panel useful space, while retaining a legible map. Checked no horizontal overflow at every requested width.
- Reproduced an OSM blank-map failure where a health probe succeeded but real tiles failed. Added a selected-view tile probe before switching and continued tile checks after pan/zoom; both simulated failure paths return to local topo.

Remaining disclosed limitations: route connectors are planning relationships, **not** exact driving, walking, or ferry paths. The bundled topo is limited to the trip footprint and cannot provide the detail of a global online map outside it. Real USGS raster labels/contours have finite native resolution, so the application caps offline stop focus to that resolution. Public live providers can fail on a different network, in which case the local topo remains available. These limitations are represented in the UI, manifests, and proof report rather than hidden.
