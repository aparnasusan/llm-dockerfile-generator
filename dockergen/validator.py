"""Validate a generated Dockerfile by actually running `docker build`."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BuildResult:
    ok: bool
    output: str


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def build(context: Path, dockerfile: Path, tag: str = "dockergen-test",
          timeout: int = 900) -> BuildResult:
    cmd = ["docker", "build", "-f", str(dockerfile), "-t", tag, str(context)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return BuildResult(False, f"docker build timed out after {timeout}s")
    return BuildResult(r.returncode == 0, (r.stdout or "") + (r.stderr or ""))
