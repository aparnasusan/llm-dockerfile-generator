"""Scan a project directory and summarize what an LLM needs to write a Dockerfile."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist",
    "build", "target", ".idea", ".vscode", ".pytest_cache", "vendor",
}

# marker file -> language, checked in order
MARKERS: list[tuple[str, str]] = [
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("package.json", "node"),
    ("pyproject.toml", "python"),
    ("requirements.txt", "python"),
    ("Pipfile", "python"),
    ("Gemfile", "ruby"),
    ("composer.json", "php"),
]

SOURCE_EXTS = {
    "python": {".py"}, "node": {".js", ".mjs", ".cjs", ".ts"}, "go": {".go"},
    "rust": {".rs"}, "java": {".java"}, "ruby": {".rb"}, "php": {".php"},
}

ENTRYPOINT_CANDIDATES = {
    "python": ["app.py", "main.py", "server.py", "manage.py", "wsgi.py", "run.py"],
    "node": ["index.js", "server.js", "app.js", "main.js", "src/index.js", "src/index.ts"],
    "go": ["main.go", "cmd/main.go"],
    "rust": ["src/main.rs"],
    "java": [],
    "ruby": ["app.rb", "config.ru"],
    "php": ["index.php"],
}

PORT_PATTERNS = [
    re.compile(r"port\s*[=:]\s*(\d{2,5})", re.I),
    re.compile(r"listen\(\s*(\d{2,5})"),
    re.compile(r"ListenAndServe\(\s*\"[^\"]*:(\d{2,5})\""),
    re.compile(r"\"[0-9.]*:(\d{2,5})\""),
    re.compile(r"PORT\s*\|\|\s*(\d{2,5})"),
    re.compile(r"getenv\([^)]*,\s*['\"]?(\d{2,5})"),
]

MAX_FILE_CHARS = 1500
MAX_TOTAL_CHARS = 6000


@dataclass
class ProjectInfo:
    root: Path
    language: str = "unknown"
    marker_files: list[str] = field(default_factory=list)
    entrypoint: str | None = None
    ports: list[int] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    excerpts: dict[str, str] = field(default_factory=dict)
    existing_dockerfile: bool = False

    def summary(self) -> str:
        lines = [
            f"Language: {self.language}",
            f"Dependency/marker files: {', '.join(self.marker_files) or 'none'}",
            f"Likely entrypoint: {self.entrypoint or 'unknown'}",
            f"Detected ports: {', '.join(map(str, self.ports)) or 'none'}",
            "File tree:",
            *[f"  {f}" for f in self.files[:60]],
        ]
        if len(self.files) > 60:
            lines.append(f"  ... ({len(self.files) - 60} more files)")
        return "\n".join(lines)


def _list_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_file():
            out.append(p)
    return out


def _read(path: Path, limit: int = MAX_FILE_CHARS) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text if len(text) <= limit else text[:limit] + "\n... (truncated)"


def _detect_ports(texts: list[str]) -> list[int]:
    found: list[int] = []
    for text in texts:
        for pat in PORT_PATTERNS:
            for m in pat.finditer(text):
                port = int(m.group(1))
                if 1 <= port <= 65535 and port not in found:
                    found.append(port)
    return found


def _node_entrypoint(root: Path) -> str | None:
    try:
        pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    start = pkg.get("scripts", {}).get("start")
    if start:
        return f"npm start ({start})"
    return pkg.get("main")


def analyze(path: str | Path) -> ProjectInfo:
    root = Path(path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")

    files = _list_files(root)
    rel_names = [p.relative_to(root).as_posix() for p in files]
    info = ProjectInfo(root=root, files=rel_names)
    info.existing_dockerfile = (root / "Dockerfile").exists()

    top_level = {p.name for p in root.iterdir() if p.is_file()}
    for marker, lang in MARKERS:
        if marker in top_level:
            info.marker_files.append(marker)
            if info.language == "unknown":
                info.language = lang

    if info.language == "unknown":
        # fall back to the most common source extension
        counts = {
            lang: sum(1 for p in files if p.suffix in exts)
            for lang, exts in SOURCE_EXTS.items()
        }
        best = max(counts, key=counts.get)
        if counts[best]:
            info.language = best

    if info.language == "node":
        info.entrypoint = _node_entrypoint(root)
    if not info.entrypoint:
        for cand in ENTRYPOINT_CANDIDATES.get(info.language, []):
            if cand in rel_names:
                info.entrypoint = cand
                break

    # excerpts: marker files first, then entrypoint, then other source files
    exts = SOURCE_EXTS.get(info.language, set())
    ordered = list(info.marker_files)
    if info.entrypoint and info.entrypoint in rel_names:
        ordered.append(info.entrypoint)
    ordered += [n for n in rel_names if Path(n).suffix in exts and n not in ordered]

    total = 0
    for name in ordered:
        text = _read(root / name)
        if not text or total + len(text) > MAX_TOTAL_CHARS:
            continue
        info.excerpts[name] = text
        total += len(text)

    source_texts = [t for n, t in info.excerpts.items() if Path(n).suffix in exts]
    info.ports = _detect_ports(source_texts)
    return info
