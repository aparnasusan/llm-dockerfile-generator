"""Validate a generated Dockerfile by actually running `docker build`."""

from __future__ import annotations

import json
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


def image_size(tag: str) -> int | None:
    """Size of a built image in bytes, or None if it can't be inspected."""
    r = subprocess.run(["docker", "image", "inspect", "-f", "{{.Size}}", tag],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip()) if r.returncode == 0 else None
    except ValueError:
        return None


def remove_image(tag: str) -> None:
    subprocess.run(["docker", "image", "rm", "-f", tag], capture_output=True)


HADOLINT_IMAGE = "hadolint/hadolint:v2.12.0"


def parse_hadolint(output: str) -> list[dict]:
    """Parse `hadolint --format json` output into a list of findings."""
    output = output.strip()
    if not output:
        return []
    findings = json.loads(output)
    return [{"code": f.get("code"), "level": f.get("level"), "line": f.get("line"),
             "message": f.get("message")} for f in findings]


def lint(dockerfile_text: str) -> list[dict] | None:
    """Lint with hadolint (a local binary if installed, otherwise its Docker image).

    Returns a list of findings ({code, level, line, message}), or None if hadolint
    couldn't run. Levels are error, warning, info and style.
    """
    if shutil.which("hadolint"):
        cmd = ["hadolint", "--no-fail", "--format", "json", "-"]
    else:
        cmd = ["docker", "run", "--rm", "-i", HADOLINT_IMAGE,
               "hadolint", "--no-fail", "--format", "json", "-"]
    try:
        r = subprocess.run(cmd, input=dockerfile_text, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        # With --no-fail hadolint exits 0 even with findings, so non-zero means it didn't
        # run (e.g. Docker is down) -- not "no findings".
        if r.returncode != 0:
            return None
        return parse_hadolint(r.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
