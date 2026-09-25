"""Rendered Day-mode hierarchy and disclosure ownership oracle."""

from __future__ import annotations

from typing import Any


AUDIT_TEXT = (
    "static schedule plan",
    "baseline unavailable",
    "no independent reference",
    "low confidence",
    "schedule-derived",
    "provenance",
    "method:",
)


def audit_day_surface(snapshot: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    rows = snapshot.get("travel_rows", [])
    if not rows:
        failures.append("selected day has no material travel rows")
    for row in rows:
        label = row.get("travel_id", "unknown")
        if row.get("expanded") is not False or row.get("region_hidden") is not True:
            failures.append(f"travel details are expanded by default for {label}")
        collapsed_text = str(row.get("collapsed_text", "")).lower()
        if any(value in collapsed_text for value in AUDIT_TEXT):
            failures.append(f"audit provenance appears in the default travel row for {label}")
        if not row.get("button_id") or row.get("controls_id") != row.get("region_id") or row.get("labelled_by") != row.get("button_id"):
            failures.append(f"Travel details ARIA ownership is broken for {label}")
        if row.get("focus_preserved") is False:
            failures.append(f"Travel details focus was lost for {label}")
    notes = snapshot.get("day_notes", {})
    if notes:
        if notes.get("expanded") is not False or notes.get("region_hidden") is not True:
            failures.append("Day notes are expanded by default")
        if not notes.get("button_id") or notes.get("controls_id") != notes.get("region_id") or notes.get("labelled_by") != notes.get("button_id"):
            failures.append("Day notes ARIA ownership is broken")
    return failures
