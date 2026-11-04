import pytest

from dockergen.generator import extract_dockerfile


def test_extracts_dockerfile_block():
    reply = "Here you go:\n```dockerfile\nFROM python:3.12-slim\nCMD [\"python\"]\n```\nEnjoy!"
    assert extract_dockerfile(reply) == 'FROM python:3.12-slim\nCMD ["python"]\n'


def test_prefers_dockerfile_block_over_others():
    reply = "```bash\ndocker build .\n```\n```Dockerfile\nFROM node:20-alpine\n```"
    assert extract_dockerfile(reply) == "FROM node:20-alpine\n"


def test_unlabeled_block_with_from():
    reply = "```\nFROM golang:1.22-alpine\nRUN go build\n```"
    assert extract_dockerfile(reply).startswith("FROM golang:1.22-alpine")


def test_no_fence_falls_back_to_from_line():
    reply = "Sure!\nFROM alpine:3.20\nCMD [\"sh\"]"
    assert extract_dockerfile(reply) == 'FROM alpine:3.20\nCMD ["sh"]\n'


def test_raises_when_missing():
    with pytest.raises(ValueError):
        extract_dockerfile("I cannot help with that.")
