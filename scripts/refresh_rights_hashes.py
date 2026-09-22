#!/usr/bin/env python3
"""Refresh hash-bound rights evidence after an approved local source change."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "manifests/public_asset_rights.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_path(value: str) -> Path:
    prefix = "artifacts/public/"
    return ROOT / (value[len(prefix):] if value.startswith(prefix) else value)


contract = json.loads(CONTRACT.read_text())
for relative in contract.get("input_sha256", {}):
    path = ROOT / relative
    if path.is_file():
        contract["input_sha256"][relative] = sha(path)
for binding in contract.get("hash_bindings", []):
    path = source_path(binding["path"])
    if path.is_file():
        binding["sha256"] = sha(path)
CONTRACT.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": "PASS", "inputs": len(contract.get("input_sha256", {})), "bindings": len(contract.get("hash_bindings", []))}))
