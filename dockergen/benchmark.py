"""Benchmark models on how often their Dockerfiles actually build.

    python -m dockergen.benchmark --models llama3.2:3b qwen2.5-coder:7b --runs 3

For every (model, project, run) it runs the same generate -> build -> repair loop as the
CLI, then records whether the build passed on the first try and after repairs, how many
repairs it needed, time spent on the model, image size, and hadolint findings.
Writes runs.csv and summary.md to results/<timestamp>/.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from dockergen import pipeline, validator
from dockergen.analyzer import analyze
from dockergen.generator import DEFAULT_MODEL, DockerfileGenerator

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

FIELDS = ["model", "project", "language", "run", "generated", "built", "first_try_built",
          "repairs", "model_seconds", "build_seconds", "image_mb", "lint_errors",
          "lint_warnings", "lint_other", "lint_codes", "error"]

console = Console()


def slug(*parts: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", "-".join(map(str, parts)).lower()).strip("-")


def run_one(model: str, project: Path, run: int, *, build: bool, retries: int,
            lint: bool, keep_images: bool, host: str | None, temperature: float,
            work_dir: Path) -> dict:
    info = analyze(project)
    tag = f"dockergen-bench-{slug(model, project.name, run)}"
    dockerfile_path = work_dir / slug(model) / project.name / f"run{run}.Dockerfile"
    row = {"model": model, "project": project.name, "language": info.language, "run": run}

    gen = DockerfileGenerator(model=model, host=host, temperature=temperature)
    result = pipeline.run(info, gen, dockerfile_path, build=build, retries=retries, tag=tag)

    row["generated"] = result.dockerfile is not None
    row["model_seconds"] = round(result.model_seconds, 2)
    row["error"] = f"{result.error_stage}: {result.error}" if result.error else ""
    if build and result.attempts:
        row["built"] = result.built
        row["first_try_built"] = result.first_try_built
        row["repairs"] = result.repairs
        row["build_seconds"] = round(sum(a.build_seconds for a in result.attempts), 2)
        if result.built:
            size = validator.image_size(tag)
            row["image_mb"] = round(size / 1e6, 1) if size else ""
            if not keep_images:
                validator.remove_image(tag)

    if lint and result.dockerfile:
        findings = validator.lint(result.dockerfile)
        if findings is not None:
            levels = [f["level"] for f in findings]
            row["lint_errors"] = levels.count("error")
            row["lint_warnings"] = levels.count("warning")
            row["lint_other"] = len(levels) - row["lint_errors"] - row["lint_warnings"]
            row["lint_codes"] = ";".join(sorted({f["code"] for f in findings if f["code"]}))
    return {k: row.get(k, "") for k in FIELDS}


# ---------------------------------------------------------------- aggregation (pure)

def _is_true(v) -> bool:
    return v is True or str(v).lower() == "true"


def _nums(rows: list[dict], key: str) -> list[float]:
    return [float(r[key]) for r in rows if r.get(key) not in ("", None)]


def _pct(hits: int, total: int) -> str:
    return f"{100 * hits / total:.0f}%" if total else "–"


def _fmt(values: list[float], fn, digits: int = 1) -> str:
    return f"{fn(values):.{digits}f}" if values else "–"


def summarize(rows: list[dict], by: tuple[str, ...] = ("model",)) -> list[dict]:
    """Aggregate per-run rows into one row per group (e.g. per model)."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in by), []).append(r)

    out = []
    for key, rs in groups.items():
        n = len(rs)
        built_rows = [r for r in rs if _is_true(r.get("built"))]
        attempted_build = [r for r in rs if r.get("built") not in ("", None)]
        linted = [r for r in rs if r.get("lint_errors") not in ("", None)]
        s = dict(zip(by, key, strict=True))
        s["runs"] = n
        s["generated"] = _pct(sum(_is_true(r["generated"]) for r in rs), n)
        s["first-try build"] = _pct(sum(_is_true(r.get("first_try_built")) for r in rs),
                                    len(attempted_build)) if attempted_build else "–"
        s["build after repair"] = _pct(len(built_rows), len(attempted_build)) \
            if attempted_build else "–"
        s["avg repairs (passing)"] = _fmt(_nums(built_rows, "repairs"), statistics.mean)
        s["median model s"] = _fmt(_nums(rs, "model_seconds"), statistics.median)
        s["median image MB"] = _fmt(_nums(built_rows, "image_mb"), statistics.median)
        s["avg lint err+warn"] = _fmt(
            [float(r["lint_errors"]) + float(r["lint_warnings"]) for r in linted],
            statistics.mean) if linted else "–"
        out.append(s)
    return sorted(out, key=lambda s: tuple(str(s[k]) for k in by))


def to_markdown(summary: list[dict]) -> str:
    if not summary:
        return "_no runs_\n"
    cols = list(summary[0])
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(" --- " for _ in cols) + "|"]
    lines += ["| " + " | ".join(str(s[c]) for c in cols) + " |" for s in summary]
    return "\n".join(lines) + "\n"


def print_table(title: str, summary: list[dict]) -> None:
    if not summary:
        return
    t = Table(title=title)
    for c in summary[0]:
        t.add_column(c)
    for s in summary:
        t.add_row(*map(str, s.values()))
    console.print(t)


# ---------------------------------------------------------------- CLI

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m dockergen.benchmark",
                                description="Benchmark Dockerfile generation across models.")
    p.add_argument("projects", nargs="*",
                   help="project folders (default: every folder in examples/)")
    p.add_argument("-m", "--models", nargs="+", default=[DEFAULT_MODEL])
    p.add_argument("-n", "--runs", type=int, default=3, help="runs per model and project")
    p.add_argument("--retries", type=int, default=2, help="max repairs per run")
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--no-build", action="store_true",
                   help="only generate (no Docker needed); measures speed and lint only")
    p.add_argument("--no-lint", action="store_true", help="skip hadolint")
    p.add_argument("--keep-images", action="store_true",
                   help="don't delete the images built during the benchmark")
    p.add_argument("--host", help="Ollama host URL")
    p.add_argument("--out", default=str(ROOT / "results"),
                   help="results directory (default: results/)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    projects = [Path(p).resolve() for p in args.projects] or \
        sorted(p for p in EXAMPLES.iterdir() if p.is_dir())
    build = not args.no_build
    if build and not validator.docker_available():
        console.print("[red]Docker is not available. Start Docker Desktop, "
                      "or use --no-build.[/red]")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / stamp
    work_dir = ROOT / "bench-work" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "runs.csv"

    total = len(args.models) * len(projects) * args.runs
    rows: list[dict] = []
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for model in args.models:
            for project in projects:
                for run in range(1, args.runs + 1):
                    label = f"[{len(rows) + 1}/{total}] {model} · {project.name} · run {run}"
                    with console.status(label + "..."):
                        row = run_one(model, project, run, build=build,
                                      retries=args.retries, lint=not args.no_lint,
                                      keep_images=args.keep_images, host=args.host,
                                      temperature=args.temperature, work_dir=work_dir)
                    rows.append(row)
                    writer.writerow(row)
                    f.flush()
                    if row["error"]:
                        outcome = f"[red]error[/red] ({row['error'][:80]})"
                    elif build:
                        outcome = ("[green]built[/green]" if _is_true(row["built"])
                                   else "[red]failed[/red]") + f", {row['repairs']} repairs"
                    else:
                        outcome = "generated"
                    console.print(f"{label}: {outcome}, {row['model_seconds']}s")

    by_model = summarize(rows, by=("model",))
    by_project = summarize(rows, by=("model", "project"))
    print_table("By model", by_model)
    print_table("By model and project", by_project)

    header = (f"# dockergen benchmark {stamp}\n\n"
              f"- Models: {', '.join(args.models)}\n"
              f"- Projects: {', '.join(p.name for p in projects)}\n"
              f"- Runs per model and project: {args.runs}; max repairs: {args.retries}; "
              f"temperature: {args.temperature}\n"
              f"- Build: {'yes' if build else 'no'}; "
              f"lint: {'no' if args.no_lint else 'hadolint'}\n\n")
    (out_dir / "summary.md").write_text(
        header + "## By model\n\n" + to_markdown(by_model)
        + "\n## By model and project\n\n" + to_markdown(by_project), encoding="utf-8")
    console.print(f"\nWrote {csv_path} and {out_dir / 'summary.md'}")
    console.print(f"Generated Dockerfiles are in {work_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
