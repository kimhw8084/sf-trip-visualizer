"""Objective detection of opaque glyph/label rectangles in a Smart-map image.

The detector is intentionally scoped to a map-canvas capture.  HTML controls,
photo markers, route callouts, and the itinerary panel are excluded by the
caller before analysis.  Thresholds are calibrated from the clean Gate-4
capture supplied for the same browser and viewport, rather than from a global
pixel-count constant.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image, ImageDraw


@dataclass(frozen=True)
class Component:
    area: int
    width: int
    height: int
    fill: float
    x: int
    y: int


def _suspicious_mask(image: Image.Image, excluded: tuple[tuple[int, int, int, int], ...] = ()) -> tuple[bytearray, int, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = list(rgb.get_flattened_data()) if hasattr(rgb, "get_flattened_data") else list(rgb.getdata())
    mask = bytearray(width * height)
    for index, (red, green, blue) in enumerate(pixels):
        spread = max(red, green, blue) - min(red, green, blue)
        if (red + green + blue) / 3 <= 120 and spread <= 24:
            mask[index] = 1
    for left, top, right, bottom in excluded:
        left, top = max(0, left), max(0, top)
        right, bottom = min(width, right), min(height, bottom)
        for y in range(top, bottom):
            start = y * width + left
            mask[start : y * width + right] = b"\0" * max(0, right - left)
    return mask, width, height


def suspicious_components(image: Image.Image, excluded: tuple[tuple[int, int, int, int], ...] = ()) -> list[Component]:
    """Return dark, low-chroma, rectangle-like connected components.

    Small glyph strokes and normal road-label antialiasing are rejected by the
    minimum area/fill bounds.  The remaining shape is the failure class seen
    as opaque black/gray rectangles over a label or glyph atlas placement.
    """

    mask, width, height = _suspicious_mask(image, excluded)
    seen = bytearray(len(mask))
    components: list[Component] = []
    for origin, value in enumerate(mask):
        if not value or seen[origin]:
            continue
        stack = [origin]
        seen[origin] = 1
        area = 0
        min_x = max_x = origin % width
        min_y = max_y = origin // width
        while stack:
            index = stack.pop()
            x, y = index % width, index // width
            area += 1
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for neighbor in (index - 1, index + 1, index - width, index + width):
                if neighbor < 0 or neighbor >= len(mask):
                    continue
                nx, ny = neighbor % width, neighbor // width
                if abs(nx - x) + abs(ny - y) != 1 or not mask[neighbor] or seen[neighbor]:
                    continue
                seen[neighbor] = 1
                stack.append(neighbor)
        component_width = max_x - min_x + 1
        component_height = max_y - min_y + 1
        fill = area / (component_width * component_height)
        if area >= 72 and component_width >= 10 and component_height >= 5 and fill >= 0.42:
            components.append(Component(area, component_width, component_height, round(fill, 3), min_x, min_y))
    return sorted(components, key=lambda component: component.area, reverse=True)


def measure(image: Image.Image) -> dict:
    components = suspicious_components(image)
    return {
        "components": len(components),
        "total_area": sum(component.area for component in components),
        "max_area": max((component.area for component in components), default=0),
        "components_detail": [asdict(component) for component in components[:40]],
        "image_size": list(image.size),
    }


def integrity_result(candidate: Image.Image, clean_reference: Image.Image) -> dict:
    """Compare a candidate map capture with its clean same-state reference."""

    clean = measure(clean_reference)
    observed = measure(candidate)
    thresholds = {
        "max_components": clean["components"] + 2,
        "max_total_area": max(180, clean["total_area"] * 3 + 96),
        "max_component_area": max(96, int(clean["max_area"] * 1.75) + 48),
    }
    failures = []
    if observed["components"] > thresholds["max_components"]:
        failures.append("suspicious_rectangle_component_count")
    if observed["total_area"] > thresholds["max_total_area"]:
        failures.append("suspicious_rectangle_area")
    if observed["max_area"] > thresholds["max_component_area"]:
        failures.append("suspicious_rectangle_max_area")
    return {
        "status": "FAIL" if failures else "PASS",
        "metric": observed,
        "clean_reference_metric": clean,
        "thresholds": thresholds,
        "failures": failures,
        "rationale": "same-browser/viewport clean Gate-4 reference plus two-component and 3x-area noise envelope",
    }


def crop_map(full_page: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """Crop a map element from a full-page screenshot using (x, y, width, height)."""

    x, y, width, height = box
    return full_page.crop((x, y, x + width, y + height))


def make_corruption_fixture(clean: Image.Image, boxes: tuple[tuple[int, int, int, int], ...]) -> Image.Image:
    """Create a deterministic regression fixture from a clean capture.

    The boxes are taken from the observed R4 finding class: opaque, low-chroma
    rectangles placed over basemap labels.  This helper keeps the regression
    test independent of platform-specific WebKit antialiasing.
    """

    result = clean.copy().convert("RGB")
    draw = ImageDraw.Draw(result)
    for left, top, right, bottom in boxes:
        draw.rectangle((left, top, right, bottom), fill=(38, 44, 50))
    return result


def image_from_path(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")
