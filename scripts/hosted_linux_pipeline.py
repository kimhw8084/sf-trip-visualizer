#!/usr/bin/env python3
"""Run decisive pipeline commands under the canonical hosted-Linux contract."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "scripts/pipeline.py"
FIREFOX_MODE_ENV = "TRIP_CROSS_BROWSER_FIREFOX_MODE"
FIREFOX_HOSTED_LINUX_MODE = "hosted-linux"
SOFTWARE_GL_ENV = "LIBGL_ALWAYS_SOFTWARE"
XVFB_SERVER_ARGS = "-screen 0 1280x1024x24"
DECISIVE_COMMANDS = ("qualify", "release")


def hosted_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    result = dict(os.environ if environment is None else environment)
    result[FIREFOX_MODE_ENV] = FIREFOX_HOSTED_LINUX_MODE
    result[SOFTWARE_GL_ENV] = "1"
    return result


def contract_failures(
    environment: dict[str, str] | None = None,
    platform: str | None = None,
) -> list[str]:
    environment = os.environ if environment is None else environment
    platform = sys.platform if platform is None else platform
    failures = []
    if not platform.startswith("linux"):
        failures.append("platform is not hosted Linux")
    if environment.get(FIREFOX_MODE_ENV) != FIREFOX_HOSTED_LINUX_MODE:
        failures.append(f"{FIREFOX_MODE_ENV} must be {FIREFOX_HOSTED_LINUX_MODE}")
    if environment.get(SOFTWARE_GL_ENV) != "1":
        failures.append(f"{SOFTWARE_GL_ENV} must be 1")
    if not environment.get("DISPLAY"):
        failures.append("DISPLAY must be provided by Xvfb")
    return failures


def pipeline_command(command: str, revision: str) -> list[str]:
    if command not in DECISIVE_COMMANDS:
        raise ValueError(f"unsupported hosted pipeline command: {command}")
    return [sys.executable, str(PIPELINE), command, "--revision", revision]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=DECISIVE_COMMANDS)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    if shutil.which("xvfb-run") is None:
        raise SystemExit("hosted Linux release contract requires xvfb-run")
    environment = hosted_environment()
    command = [
        "xvfb-run",
        "--auto-servernum",
        f"--server-args={XVFB_SERVER_ARGS}",
        *pipeline_command(args.command, args.revision),
    ]
    return subprocess.call(command, cwd=ROOT, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
