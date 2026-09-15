"""Collect unique itinerary prose for local macOS Translation.framework passes."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data/phase7_app_data.json").read_text())
KO = set()
EN = set()
PROSE_KEYS = {
    "title", "subtitle", "core_reason", "lodging", "summary", "why", "role",
    "reason", "advantage", "kind", "status", "stop_reason", "stop_advantage",
    "note", "label", "mode", "text", "cluster", "route_title",
}


def walk(value, key=""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            walk(child, child_key)
    elif isinstance(value, list):
        for child in value:
            walk(child, key)
    elif isinstance(value, str) and key in PROSE_KEYS:
        if re.search(r"[가-힣]", value):
            KO.add(value)
        elif re.search(r"[A-Za-z]{3}", value) and "http" not in value and len(value) > 12:
            EN.add(value)


walk(DATA)
tmp = ROOT / ".tools"
tmp.mkdir(exist_ok=True)
(tmp / "i18n_ko.json").write_text(json.dumps(sorted(KO), ensure_ascii=False, indent=2))
(tmp / "i18n_en.json").write_text(json.dumps(sorted(EN), ensure_ascii=False, indent=2))
print(f"Korean to English: {len(KO)}; English to Korean: {len(EN)}")
