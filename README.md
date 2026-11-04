# dockergen — Dockerfile generation with a local LLM

[![CI](https://github.com/aparnasusan/llm-dockerfile-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/aparnasusan/llm-dockerfile-generator/actions/workflows/ci.yml)

`dockergen` scans a project folder (language, dependency files, entrypoint, ports), then asks an
open-weight LLM running locally in **Ollama** to write a Dockerfile for it. With `--build` it
also runs `docker build`. If the build fails, the error goes back to the model to fix.

## Install

Needs Python 3.12+ and [Ollama](https://ollama.com). Docker Desktop is only needed for `--build`.

```powershell
pip install "llm-dockerfile-generator[ui] @ git+https://github.com/aparnasusan/llm-dockerfile-generator"
ollama pull llama3.2:3b      # default model (small and fast)
```

This installs three commands: `dockergen` (CLI), `dockergen-ui` (web UI) and `dockergen-bench`
(benchmark). Leave off `[ui]` if you only want the CLI.

## Usage

```powershell
# write path/to/project/Dockerfile
dockergen path/to/project

# generate, build, and auto-repair on failure
dockergen path/to/project --build

# write somewhere else, overwrite without asking
dockergen path/to/project --out out/Dockerfile --force

# then run the built image
docker run --rm -p 3000:3000 dockergen-test
```

Options: `--model`, `--out`, `--force`, `--build`, `--retries N`, `--tag`, `--host`
(see `dockergen -h`).

### Web UI

```powershell
dockergen-ui
```

Opens in your browser. Paste a project path (or, in a source checkout, pick an example), choose an installed Ollama
model, optionally turn on **Build with Docker and auto-repair**, and click **Generate**. You can
see each build attempt with its Dockerfile and `docker build` output, and download the result.

## Choosing a model (Ollama + Hugging Face)

Any Ollama model works through `--model`. Ollama can also pull GGUF models straight from
Hugging Face:

```powershell
ollama pull qwen2.5-coder:7b                                   # Ollama library
ollama pull hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M   # straight from Hugging Face
dockergen path/to/project --build --model hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M
```

Small models (3B) are fast but make more mistakes. Coding models of 7B or larger produce
noticeably better Dockerfiles, especially multi-stage builds.

## Benchmark

`dockergen-bench` measures how often each model's Dockerfiles actually build. For every
model × project × run it uses the same generate → build → repair loop as the CLI and records:

- **First-try build rate** and **build rate after repairs**
- **Repairs needed** for the runs that passed
- **Model time**, **image size**, and **[hadolint](https://github.com/hadolint/hadolint)**
  errors and warnings (it uses a local `hadolint` binary if installed, otherwise the
  `hadolint/hadolint` Docker image)

```powershell
ollama pull qwen2.5-coder:7b
dockergen-bench --models llama3.2:3b qwen2.5-coder:7b --runs 3   # every folder in ./examples
dockergen-bench path/to/project --runs 5                          # specific projects
dockergen-bench --no-build                                        # no Docker: speed only
```

With no project arguments it uses the folders in `./examples`, so run it from a source checkout
(see Development) or pass projects. Each run writes `results/<timestamp>/runs.csv` (one row per run) and `summary.md` (tables by model
and by model × project). Generated Dockerfiles go to `bench-work/`, and images built during the
benchmark are deleted unless you pass `--keep-images`.

## How it works

| Module | Role |
| --- | --- |
| `dockergen/analyzer.py` | Walks the project, detects the stack from marker files, finds the entrypoint and ports, collects file excerpts (with a size cap) |
| `dockergen/prompts.py` | System prompt with Dockerfile best practices, plus generation and repair prompts |
| `dockergen/generator.py` | Ollama chat client that keeps conversation history; pulls the Dockerfile out of the model's reply |
| `dockergen/validator.py` | Runs `docker build` and captures the output |
| `dockergen/pipeline.py` | The generate → build → repair loop, shared by the CLI, web UI and benchmark |
| `dockergen/cli.py` | Command-line front end |
| `dockergen/benchmark.py` | Runs models across projects and writes pass-rate / size / lint tables |
| `dockergen/webui.py` | Streamlit web UI over the same pipeline (`dockergen/ui.py` launches it) |

## Development

```powershell
git clone https://github.com/aparnasusan/llm-dockerfile-generator
cd llm-dockerfile-generator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"       # editable install: code changes apply without reinstalling

python -m pytest              # unit tests
ruff check .                  # lint
dockergen examples/go-http    # try it on the bundled example projects
streamlit run app.py          # web UI, with the examples in its dropdown
```

CI runs ruff and the tests on Ubuntu and Windows on every push, after a regular `pip install` of
the package. The tests cover the analyzer, Dockerfile extraction, the repair loop (with a fake
model and fake `docker build`), and the benchmark's aggregation. They don't need Ollama or Docker.

## Ideas to extend

- Also generate `.dockerignore` and `docker-compose.yml`
- Feed hadolint warnings back to the model, like build errors

## License

[MIT](LICENSE) © 2026 Aparna Susan Varughese
