# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

`dockergen`: a beginner-level Python CLI that generates Dockerfiles with a **local open-weight LLM
via Ollama**. It analyzes a project folder, prompts the model, writes the Dockerfile, and with
`--build` runs `docker build` and feeds any build errors back to the model to repair, up to
`--retries` times.

## Commands (Windows / PowerShell)

```powershell
python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q                          # unit tests (no Ollama/Docker needed)
.\.venv\Scripts\python.exe -m dockergen examples/python-flask    # generate only
.\.venv\Scripts\python.exe -m dockergen examples/go-http --build --force   # generate + build + repair
.\.venv\Scripts\streamlit.exe run app.py                       # web UI
```

- Set `$env:PYTHONIOENCODING='utf-8'` when capturing CLI output, or rich's box characters can fail.
- `--build` needs Docker Desktop running (`docker info` must succeed).
- The default model is `llama3.2:3b` (`DEFAULT_MODEL` in `dockergen/generator.py`). Use `--model`
  for others, including Hugging Face GGUF models (`hf.co/<user>/<repo>:<quant>`).

## Architecture

Pipeline: `analyzer` → `prompts` → `generator` → `validator`. The generate → build → repair loop
lives once in `dockergen/pipeline.py` and is used by the CLI, the web UI and the benchmark.

- `dockergen/analyzer.py`: `analyze(path) -> ProjectInfo`. Detects language from `MARKERS`
  (first match wins, in order), falling back to counting source file extensions. Finds the
  entrypoint (`ENTRYPOINT_CANDIDATES`, `package.json` `scripts.start`) and ports (`PORT_PATTERNS`
  regexes over source excerpts). Excerpts are capped by `MAX_FILE_CHARS` / `MAX_TOTAL_CHARS` so
  small models aren't overloaded. Skips `SKIP_DIRS`.
- `dockergen/prompts.py`: `SYSTEM_PROMPT` (best-practice rules), `LANGUAGE_HINTS` (per-stack
  structure; this matters a lot for 3B models), `COMMON_LOCKFILES` (lists missing lock files so the
  model doesn't COPY files that don't exist), `build_generation_prompt`, and `build_repair_prompt`
  (which sends only the last 3000 chars of build output).
- `dockergen/generator.py`: `extract_dockerfile(reply)` (pure function, unit-tested) and
  `DockerfileGenerator`, which keeps chat history so repairs have context. `ollama` is imported
  lazily so tests don't need it.
- `dockergen/validator.py`: `docker_available()` and `build(context, dockerfile, tag)` via
  `subprocess` with `docker build -f`.
- `dockergen/pipeline.py`: `run(info, gen, dockerfile_path, build=, retries=, tag=, on_event=)` ->
  `RunResult` (attempts, timings, `built`, `first_try_built`, `repairs`, `error_stage`). Front ends
  show progress through the `on_event` callback. Tested with a fake generator and fake `build`.
- `dockergen/cli.py`: argparse plus rich output; owns the overwrite prompt.
- `app.py` (project root, so Streamlit can import `dockergen`): Streamlit UI over `pipeline.run`;
  keeps the result in `st.session_state`.
- `examples/`: small Flask, Express, and Go apps used by tests and for manual runs. Generated
  `Dockerfile`s in there are build artifacts and can be overwritten.

## Conventions

- Python 3.12, standard library first; runtime deps are only `ollama`, `rich`, and
  `streamlit` (UI only).
- Keep the logic that tests can check (analysis, prompt building, extraction) free of
  network/Docker calls. Add tests in `tests/` for new detection rules or extraction cases.
- To improve output quality, prefer tightening `LANGUAGE_HINTS` / `SYSTEM_PROMPT` over
  post-processing the model's output.
- When adding a language, update `MARKERS`, `SOURCE_EXTS`, `ENTRYPOINT_CANDIDATES`,
  `LANGUAGE_HINTS`, `COMMON_LOCKFILES`, and add an example project and a test.

## Known limitations

- `llama3.2:3b` sometimes leaves out steps (for example the `go build` line in Go multi-stage
  builds). `--build` catches and repairs these; `qwen2.5-coder:7b` or larger is more reliable.
- Port detection is regex-based and can miss ports set in config files or env vars.
