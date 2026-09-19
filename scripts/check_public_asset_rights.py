#!/usr/bin/env python3
"""Fail-closed audit of an exact public candidate tree against Gate 6 rights truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from public_asset_rights import ROOT, audit_tree, load_contract, load_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", required=True, help="exact candidate/public tree to enumerate")
    parser.add_argument("--mode", choices=("pages", "public-package"), required=True)
    parser.add_argument("--report", help="optional JSON report path")
    parser.add_argument("--allow-missing-provenance", action="store_true", help="only for pre-provenance assembly staging")
    args = parser.parse_args()
    tree = Path(args.tree)
    if not tree.is_absolute():
        tree = ROOT / tree
    result = audit_tree(tree.resolve(), mode=args.mode, require_provenance=not args.allow_missing_provenance)
    if args.report:
        report = Path(args.report)
        if not report.is_absolute():
            report = ROOT / report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
