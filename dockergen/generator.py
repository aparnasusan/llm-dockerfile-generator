"""Talk to a local Ollama model and extract Dockerfiles from its replies."""

from __future__ import annotations

import re

from dockergen.analyzer import ProjectInfo
from dockergen.prompts import SYSTEM_PROMPT, build_generation_prompt, build_repair_prompt

DEFAULT_MODEL = "llama3.2:3b"

_FENCE = re.compile(r"```[ \t]*([\w-]*)[ \t]*\r?\n(.*?)```", re.S)


def extract_dockerfile(reply: str) -> str:
    """Pull the Dockerfile out of a model reply.

    Prefers a ```dockerfile block, then any block that contains FROM,
    then falls back to the raw text starting at the first FROM line.
    """
    blocks = _FENCE.findall(reply)
    for lang, body in blocks:
        if lang.lower() in {"dockerfile", "docker"}:
            return body.strip() + "\n"
    for _, body in blocks:
        if re.search(r"^\s*FROM\s", body, re.M | re.I):
            return body.strip() + "\n"
    m = re.search(r"^\s*FROM\s", reply, re.M | re.I)
    if m:
        return reply[m.start():].strip() + "\n"
    raise ValueError("Model reply did not contain a Dockerfile")


class DockerfileGenerator:
    """Keeps a chat history so build errors can be fed back for repair."""

    def __init__(self, model: str = DEFAULT_MODEL, host: str | None = None,
                 temperature: float = 0.2):
        import ollama  # imported lazily so tests don't need the package/server

        self.model = model
        self.client = ollama.Client(host=host) if host else ollama.Client()
        self.options = {"temperature": temperature}
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _chat(self, content: str) -> str:
        self.messages.append({"role": "user", "content": content})
        resp = self.client.chat(model=self.model, messages=self.messages,
                                options=self.options)
        reply = resp["message"]["content"]
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def generate(self, info: ProjectInfo) -> str:
        return extract_dockerfile(self._chat(build_generation_prompt(info)))

    def repair(self, dockerfile: str, build_error: str) -> str:
        return extract_dockerfile(self._chat(build_repair_prompt(dockerfile, build_error)))
