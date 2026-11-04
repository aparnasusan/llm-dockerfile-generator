from pathlib import Path

import pytest

from dockergen import pipeline
from dockergen.analyzer import ProjectInfo
from dockergen.validator import BuildResult


class FakeGen:
    """Returns canned Dockerfiles: the first from generate(), the rest from repair()."""

    def __init__(self, replies, fail_on=None):
        self.replies = list(replies)
        self.fail_on = fail_on
        self.repair_errors = []

    def generate(self, info):
        if self.fail_on == "generate":
            raise ConnectionError("ollama down")
        return self.replies.pop(0)

    def repair(self, dockerfile, error):
        if self.fail_on == "repair":
            raise ValueError("no Dockerfile in reply")
        self.repair_errors.append(error)
        return self.replies.pop(0)


@pytest.fixture
def fake_build(monkeypatch):
    """docker build passes only for Dockerfiles containing 'GOOD'."""
    calls = []

    def build(context, dockerfile, tag="t"):
        text = Path(dockerfile).read_text(encoding="utf-8")
        calls.append(text)
        return BuildResult("GOOD" in text, "ok" if "GOOD" in text else "step failed")

    monkeypatch.setattr(pipeline.validator, "build", build)
    return calls


def info(tmp_path):
    return ProjectInfo(root=tmp_path)


def test_generate_only_writes_file(tmp_path):
    out = tmp_path / "Dockerfile"
    r = pipeline.run(info(tmp_path), FakeGen(["FROM a\n"]), out)
    assert out.read_text() == "FROM a\n"
    assert r.dockerfile == "FROM a\n" and r.attempts[0].build is None
    assert not r.built and r.error is None


def test_first_try_success(tmp_path, fake_build):
    r = pipeline.run(info(tmp_path), FakeGen(["FROM GOOD\n"]), tmp_path / "D", build=True)
    assert r.built and r.first_try_built and r.repairs == 0
    assert len(fake_build) == 1


def test_repair_then_success(tmp_path, fake_build):
    gen = FakeGen(["FROM bad\n", "FROM GOOD\n"])
    r = pipeline.run(info(tmp_path), gen, tmp_path / "D", build=True, retries=2)
    assert r.built and not r.first_try_built and r.repairs == 1
    assert gen.repair_errors == ["step failed"]       # build output fed back to the model
    assert (tmp_path / "D").read_text() == "FROM GOOD\n"


def test_gives_up_after_retries(tmp_path, fake_build):
    r = pipeline.run(info(tmp_path), FakeGen(["FROM bad\n"] * 5), tmp_path / "D",
                     build=True, retries=2)
    assert not r.built and len(r.attempts) == 3 and len(fake_build) == 3


def test_generation_error_is_recorded(tmp_path):
    r = pipeline.run(info(tmp_path), FakeGen([], fail_on="generate"), tmp_path / "D")
    assert r.error_stage == "generate" and r.attempts == [] and r.dockerfile is None


def test_repair_error_is_recorded(tmp_path, fake_build):
    r = pipeline.run(info(tmp_path), FakeGen(["FROM bad\n"], fail_on="repair"),
                     tmp_path / "D", build=True)
    assert r.error_stage == "repair" and not r.built and len(r.attempts) == 1


def test_events(tmp_path, fake_build):
    events = []
    pipeline.run(info(tmp_path), FakeGen(["FROM bad\n", "FROM GOOD\n"]), tmp_path / "D",
                 build=True, on_event=lambda kind, **d: events.append(kind))
    assert events == ["generating", "building", "built", "repairing", "repaired",
                      "building", "built"]
