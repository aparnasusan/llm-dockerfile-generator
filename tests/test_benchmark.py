from dockergen.benchmark import slug, summarize, to_markdown
from dockergen.validator import parse_hadolint


def row(model="m", project="p", built=True, first=True, repairs=0, secs=2.0,
        mb=50.0, err=0, warn=1, generated=True):
    return {"model": model, "project": project, "generated": generated, "built": built,
            "first_try_built": first, "repairs": repairs, "model_seconds": secs,
            "image_mb": mb if built else "", "lint_errors": err, "lint_warnings": warn}


def test_summarize_rates_and_averages():
    rows = [row(), row(first=False, repairs=1, secs=4.0, mb=70.0),
            row(built=False, first=False, repairs=2, warn=3)]
    (s,) = summarize(rows)
    assert s["runs"] == 3
    assert s["first-try build"] == "33%"
    assert s["build after repair"] == "67%"
    assert s["avg repairs (passing)"] == "0.5"     # only passing runs count
    assert s["median model s"] == "2.0"
    assert s["median image MB"] == "60.0"
    assert s["avg lint err+warn"] == "1.7"


def test_summarize_groups_and_handles_csv_strings():
    # values read back from CSV are strings
    rows = [row(model="a"), row(model="b", built="False", first="False", mb="")]
    rows[0].update(built="True", first_try_built="True", model_seconds="1.5")
    out = summarize(rows)
    assert [s["model"] for s in out] == ["a", "b"]
    assert out[0]["build after repair"] == "100%" and out[1]["build after repair"] == "0%"
    assert out[1]["median image MB"] == "–"


def test_summarize_without_build_or_lint():
    rows = [{"model": "m", "generated": True, "built": "", "model_seconds": 3,
             "lint_errors": "", "lint_warnings": ""}]
    (s,) = summarize(rows)
    assert s["first-try build"] == "–" and s["build after repair"] == "–"
    assert s["avg lint err+warn"] == "–"


def test_to_markdown():
    md = to_markdown([{"model": "m", "runs": 2}])
    assert md.splitlines() == ["| model | runs |", "| --- | --- |", "| m | 2 |"]


def test_parse_hadolint():
    out = ('[{"code":"DL3018","column":1,"file":"-","level":"warning","line":3,'
           '"message":"Pin versions in apk add"}]')
    assert parse_hadolint(out) == [{"code": "DL3018", "level": "warning", "line": 3,
                                    "message": "Pin versions in apk add"}]
    assert parse_hadolint("") == [] and parse_hadolint("[]") == []


def test_slug():
    assert slug("hf.co/Qwen/Coder:Q4_K_M", "go-http", 1) == "hf-co-qwen-coder-q4-k-m-go-http-1"
