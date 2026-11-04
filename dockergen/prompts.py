"""Prompt templates for Dockerfile generation and repair."""

from __future__ import annotations

from dockergen.analyzer import ProjectInfo

SYSTEM_PROMPT = """You are an expert DevOps engineer who writes production-quality Dockerfiles.

Rules:
- Output exactly ONE Dockerfile inside a single ```dockerfile fenced code block. No other code blocks.
- Use an official base image with a pinned version tag (prefer slim/alpine variants), e.g. python:3.12-slim, node:20-alpine, golang:1.22-alpine.
- Copy dependency manifests and install dependencies BEFORE copying the rest of the source, to maximize layer caching.
- Use a multi-stage build for compiled languages (Go, Rust, Java) so the final image only contains the runtime artifact.
- Run as a non-root user in the final image.
- EXPOSE the port the app listens on (if any) and end with a CMD (or ENTRYPOINT) that starts the app.
- Only reference files that actually exist in the project file tree you are given.
- Do not invent lock files (e.g. package-lock.json, go.sum) that are not in the file tree.
- Keep it concise; short comments are fine."""


COMMON_LOCKFILES = {
    "go": ["go.sum"],
    "node": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
    "python": ["poetry.lock", "Pipfile.lock"],
    "rust": ["Cargo.lock"],
}

LANGUAGE_HINTS = {
    "python": (
        "Single stage. Base image python:3.12-slim. WORKDIR /app, COPY requirements.txt, "
        "RUN pip install --no-cache-dir -r requirements.txt, COPY . ., create a non-root user, "
        "CMD [\"python\", \"<entrypoint>\"]."
    ),
    "node": (
        "Single stage (no multi-stage, no `npm run build` unless package.json has a build "
        "script). Base image node:20-alpine. WORKDIR /app first, COPY package*.json ./, "
        "RUN npm install --omit=dev, COPY . ., USER node, CMD [\"npm\", \"start\"]."
    ),
    "go": (
        "Multi-stage. Stage 1: FROM golang:1.22-alpine AS build, WORKDIR /src, "
        "COPY go.mod ./ (add go.sum only if it exists), RUN go mod download, COPY . ., "
        "RUN CGO_ENABLED=0 go build -o /app . "
        "Stage 2: FROM alpine:3.20, RUN adduser -D app (alpine has no useradd), "
        "COPY --from=build /app /app, USER app, ENTRYPOINT [\"/app\"]."
    ),
    "rust": "Multi-stage: rust:1-slim to build with cargo build --release, debian:bookworm-slim to run.",
    "java": "Multi-stage: maven/gradle image to build the jar, eclipse-temurin:21-jre to run it.",
}


def build_generation_prompt(info: ProjectInfo) -> str:
    parts = [
        "Write a Dockerfile for the following project.",
        "",
        "## Project summary",
        info.summary(),
        "",
    ]
    hint = LANGUAGE_HINTS.get(info.language)
    if hint:
        parts += ["## Recommended structure", hint, ""]
    missing = [f for f in COMMON_LOCKFILES.get(info.language, []) if f not in info.files]
    if missing:
        parts += [f"Note: these files do NOT exist, do not COPY them: {', '.join(missing)}", ""]
    parts += ["## Key files"]
    for name, text in info.excerpts.items():
        parts += [f"### {name}", "```", text, "```", ""]
    return "\n".join(parts)


def build_repair_prompt(dockerfile: str, build_error: str) -> str:
    # docker build output can be long; the useful part is at the end
    tail = build_error[-3000:]
    return (
        "The Dockerfile you wrote failed to build.\n\n"
        f"## Dockerfile\n```dockerfile\n{dockerfile}\n```\n\n"
        f"## docker build output (tail)\n```\n{tail}\n```\n\n"
        "Fix the problem and output the complete corrected Dockerfile "
        "in a single ```dockerfile code block."
    )
