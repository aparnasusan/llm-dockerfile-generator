"""Command-line interface: python -m dockergen <project-path> [options]"""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from dockergen.analyzer import analyze
from dockergen.generator import DEFAULT_MODEL, DockerfileGenerator
from dockergen import validator

console = Console()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="dockergen",
        description="Generate a Dockerfile for a project using a local LLM (Ollama).",
    )
    p.add_argument("path", help="path to the project directory")
    p.add_argument("-m", "--model", default=DEFAULT_MODEL,
                   help=f"Ollama model name (default: {DEFAULT_MODEL}); "
                        "Hugging Face GGUF models work too, e.g. hf.co/<user>/<repo>")
    p.add_argument("-o", "--out", help="where to write the Dockerfile "
                                       "(default: <path>/Dockerfile)")
    p.add_argument("-f", "--force", action="store_true",
                   help="overwrite an existing Dockerfile without asking")
    p.add_argument("-b", "--build", action="store_true",
                   help="run `docker build` and let the model fix errors")
    p.add_argument("--retries", type=int, default=2,
                   help="max repair attempts when --build fails (default: 2)")
    p.add_argument("--tag", default="dockergen-test", help="image tag for --build")
    p.add_argument("--host", help="Ollama host URL (default: http://localhost:11434)")
    return p.parse_args(argv)


def show_dockerfile(text: str, title: str) -> None:
    console.print(Panel(Syntax(text, "docker", theme="monokai", line_numbers=True),
                        title=title))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        info = analyze(args.path)
    except NotADirectoryError as e:
        console.print(f"[red]{e}[/red]")
        return 2

    console.print(Panel(info.summary(), title=f"Project analysis: {info.root.name}"))

    out = Path(args.out).resolve() if args.out else info.root / "Dockerfile"
    if out.exists() and not args.force:
        answer = console.input(f"[yellow]{out} already exists. Overwrite? [y/N] [/yellow]")
        if answer.strip().lower() not in {"y", "yes"}:
            console.print("Aborted.")
            return 1

    try:
        gen = DockerfileGenerator(model=args.model, host=args.host)
        with console.status(f"Asking [bold]{args.model}[/bold] for a Dockerfile..."):
            dockerfile = gen.generate(info)
    except Exception as e:  # connection errors, missing model, bad reply
        console.print(f"[red]Generation failed:[/red] {e}")
        console.print("Is Ollama running? Try `ollama serve` and "
                      f"`ollama pull {args.model}`.")
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dockerfile, encoding="utf-8")
    show_dockerfile(dockerfile, f"Generated Dockerfile -> {out}")

    if not args.build:
        return 0

    if not validator.docker_available():
        console.print("[red]Docker is not available (is Docker Desktop running?). "
                      "Skipping build.[/red]")
        return 1

    for attempt in range(args.retries + 1):
        with console.status(f"docker build (attempt {attempt + 1})..."):
            result = validator.build(info.root, out, tag=args.tag)
        if result.ok:
            console.print(f"[green]Build succeeded![/green] Image tag: [bold]{args.tag}[/bold]")
            ports = info.ports or []
            if ports:
                console.print(f"Try it: docker run --rm -p {ports[0]}:{ports[0]} {args.tag}")
            else:
                console.print(f"Try it: docker run --rm {args.tag}")
            return 0

        console.print(f"[red]Build failed (attempt {attempt + 1}).[/red]")
        console.print(result.output[-1500:], markup=False, highlight=False)
        if attempt == args.retries:
            break
        try:
            with console.status("Asking the model to fix the Dockerfile..."):
                dockerfile = gen.repair(dockerfile, result.output)
        except Exception as e:
            console.print(f"[red]Repair failed:[/red] {e}")
            return 1
        out.write_text(dockerfile, encoding="utf-8")
        show_dockerfile(dockerfile, f"Repaired Dockerfile (attempt {attempt + 2})")

    console.print("[red]Could not produce a building Dockerfile. "
                  "Try a larger model with --model.[/red]")
    return 1
