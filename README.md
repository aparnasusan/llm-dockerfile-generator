# dockergen — Dockerfile generation with a local LLM

[![CI](https://github.com/aparnasusan/llm-dockerfile-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/aparnasusan/llm-dockerfile-generator/actions/workflows/ci.yml)

`dockergen` scans a project folder (language, dependency files, entrypoint, ports), then asks an
open-weight LLM running locally in **Ollama** to write a Dockerfile for it. With `--build` it
also runs `docker build`. If the build fails, the error goes back to the model to fix.

## Setup (Windows / PowerShell)

```powershell
cd dockerfile-gen
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

ollama pull llama3.2:3b      # default model (small and fast)
```

Docker Desktop must be running if you use `--build`.

## Usage

```powershell
# generate examples/python-flask/Dockerfile
python -m dockergen examples/python-flask

# generate, build, and auto-repair on failure
python -m dockergen examples/node-express --build

# write somewhere else, overwrite without asking
python -m dockergen examples/go-http --out out/Dockerfile.go --force

# then run the built image
docker run --rm -p 3000:3000 dockergen-test
```

### Web UI

```powershell
streamlit run app.py
```

Opens in your browser. Pick an example (or paste a project path), choose an installed Ollama
model, optionally turn on **Build with Docker and auto-repair**, and click **Generate**. You can
see each build attempt with its Dockerfile and `docker build` output, and download the result.

Options: `--model`, `--out`, `--force`, `--build`, `--retries N`, `--tag`, `--host`
(see `python -m dockergen -h`).

## Choosing a model (Ollama + Hugging Face)

Any Ollama model works through `--model`. Ollama can also pull GGUF models straight from
Hugging Face:

```powershell
ollama pull qwen2.5-coder:7b                                   # Ollama library
ollama pull hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M   # straight from Hugging Face
python -m dockergen examples/go-http --build --model hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M
```

Small models (3B) are fast but make more mistakes. Coding models of 7B or larger produce
noticeably better Dockerfiles, especially multi-stage builds.

## Benchmark

`dockergen.benchmark` measures how often each model's Dockerfiles actually build. For every
model × project × run it uses the same generate → build → repair loop as the CLI and records:

- **First-try build rate** and **build rate after repairs**
- **Repairs needed** for the runs that passed
- **Model time**, **image size**, and **[hadolint](https://github.com/hadolint/hadolint)**
  errors and warnings (it uses a local `hadolint` binary if installed, otherwise the
  `hadolint/hadolint` Docker image)

```powershell
ollama pull qwen2.5-coder:7b
python -m dockergen.benchmark --models llama3.2:3b qwen2.5-coder:7b --runs 3
python -m dockergen.benchmark examples/go-http --runs 5      # one project
python -m dockergen.benchmark --no-build                     # no Docker: speed only
```

Each run writes `results/<timestamp>/runs.csv` (one row per run) and `summary.md` (tables by model
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
| `app.py` | Streamlit web UI over the same pipeline |

## Tests

```powershell
python -m pytest
ruff check .          # lint (pip install ruff)
```

CI runs both on every push. The tests cover the analyzer, Dockerfile extraction, the repair
loop (with a fake model and fake `docker build`), and the benchmark's aggregation. They don't need Ollama or Docker.

## Ideas to extend

- Also generate `.dockerignore` and `docker-compose.yml`
- Feed hadolint warnings back to the model, like build errors
