# dockergen — Dockerfile generation with a local LLM

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

## How it works

| Module | Role |
| --- | --- |
| `dockergen/analyzer.py` | Walks the project, detects the stack from marker files, finds the entrypoint and ports, collects file excerpts (with a size cap) |
| `dockergen/prompts.py` | System prompt with Dockerfile best practices, plus generation and repair prompts |
| `dockergen/generator.py` | Ollama chat client that keeps conversation history; pulls the Dockerfile out of the model's reply |
| `dockergen/validator.py` | Runs `docker build` and captures the output |
| `dockergen/cli.py` | Ties it all together: generate → write → build → repair loop |
| `app.py` | Streamlit web UI over the same pipeline |

## Tests

```powershell
python -m pytest
```

The tests cover the analyzer and the Dockerfile extraction. They don't need Ollama or Docker.

## Ideas to extend

- Also generate `.dockerignore` and `docker-compose.yml`
- Compare models (pass rate of `docker build` across the example projects)
- Lint the output with [hadolint](https://github.com/hadolint/hadolint)
