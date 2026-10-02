"""Qualify the editable planner with the repository's pinned Playwright runtime."""
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urljoin

import playwright
from qa_evidence import bind_report, candidate_identity

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "QA/CHG-232/planner"


def main():
    identity = candidate_identity()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    driver = Path(playwright.__file__).parent / "driver"
    node = str(driver / "node")
    environment = dict(os.environ)
    environment["PLAYWRIGHT_MODULE"] = str(driver / "package")
    environment["PLANNER_QA_OUTPUT"] = str(OUTPUT)
    url = urljoin(environment.get("TRIP_QA_URL", "http://127.0.0.1:8768/index.html"), "planner.html")
    checks = []
    for name, args in (
        ("unit", ["--test", "tests/planner-core.test.mjs", "tests/planner-google.test.mjs"]),
        ("browser", ["scripts/qa_planner.mjs", url]),
    ):
        process = subprocess.run([node, *args], cwd=ROOT, env=environment, text=True, capture_output=True, timeout=180)
        (OUTPUT / f"{name}.log").write_text(process.stdout + process.stderr)
        checks.append({"name": name, "status": "PASS" if process.returncode == 0 else "FAIL", "returncode": process.returncode})
    report = bind_report({"status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL", "checks": checks, "live_google": "UNVERIFIED_REQUIRES_OWNER_KEY"}, identity)
    (OUTPUT / "release.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
