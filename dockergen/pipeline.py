"""The generate -> build -> repair loop, shared by the CLI, the web UI and the benchmark."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dockergen import validator
from dockergen.analyzer import ProjectInfo
from dockergen.validator import BuildResult

# on_event(kind, **data). Kinds: "generating", "building", "built", "repairing", "repaired".
EventHandler = Callable[..., None]


@dataclass
class Attempt:
    dockerfile: str
    build: BuildResult | None = None
    build_seconds: float = 0.0


@dataclass
class RunResult:
    attempts: list[Attempt] = field(default_factory=list)
    model_seconds: float = 0.0        # total time spent waiting on the model
    error: str | None = None          # set if generation or a repair call failed
    error_stage: str | None = None    # "generate" or "repair"

    @property
    def dockerfile(self) -> str | None:
        return self.attempts[-1].dockerfile if self.attempts else None

    @property
    def built(self) -> bool:
        """Did any build attempt succeed?"""
        return bool(self.attempts and self.attempts[-1].build and self.attempts[-1].build.ok)

    @property
    def first_try_built(self) -> bool:
        return bool(self.attempts and self.attempts[0].build and self.attempts[0].build.ok)

    @property
    def repairs(self) -> int:
        return max(len(self.attempts) - 1, 0)


def _noop(kind: str, **data) -> None:
    pass


def run(info: ProjectInfo, gen, dockerfile_path: Path, *, build: bool = False,
        retries: int = 2, tag: str = "dockergen-test",
        on_event: EventHandler = _noop) -> RunResult:
    """Generate a Dockerfile, write it to dockerfile_path and, if build is set,
    run docker build, feeding failures back to the model up to `retries` times.

    `gen` is a DockerfileGenerator (anything with generate(info) and repair(df, err)).
    The caller checks validator.docker_available() before passing build=True.
    """
    result = RunResult()
    dockerfile_path.parent.mkdir(parents=True, exist_ok=True)

    on_event("generating")
    t = time.perf_counter()
    try:
        dockerfile = gen.generate(info)
    except Exception as e:  # connection errors, missing model, reply with no Dockerfile
        result.error, result.error_stage = str(e), "generate"
        return result
    finally:
        result.model_seconds += time.perf_counter() - t

    while True:
        attempt = Attempt(dockerfile)
        result.attempts.append(attempt)
        dockerfile_path.write_text(dockerfile, encoding="utf-8")
        n = len(result.attempts)
        if not build:
            return result

        on_event("building", attempt=n)
        t = time.perf_counter()
        attempt.build = validator.build(info.root, dockerfile_path, tag=tag)
        attempt.build_seconds = time.perf_counter() - t
        on_event("built", attempt=n, result=attempt.build)
        if attempt.build.ok or n > retries:
            return result

        on_event("repairing", attempt=n)
        t = time.perf_counter()
        try:
            dockerfile = gen.repair(dockerfile, attempt.build.output)
        except Exception as e:
            result.error, result.error_stage = str(e), "repair"
            return result
        finally:
            result.model_seconds += time.perf_counter() - t
        on_event("repaired", attempt=n + 1, dockerfile=dockerfile)
