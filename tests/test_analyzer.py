from pathlib import Path

import pytest

from dockergen.analyzer import analyze

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_python_flask():
    info = analyze(EXAMPLES / "python-flask")
    assert info.language == "python"
    assert "requirements.txt" in info.marker_files
    assert info.entrypoint == "app.py"
    assert 5000 in info.ports
    assert "app.py" in info.excerpts


def test_node_express():
    info = analyze(EXAMPLES / "node-express")
    assert info.language == "node"
    assert info.entrypoint.startswith("npm start")
    assert 3000 in info.ports


def test_go_http():
    info = analyze(EXAMPLES / "go-http")
    assert info.language == "go"
    assert info.entrypoint == "main.go"
    assert 8080 in info.ports


def test_skips_noise_dirs(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x")
    info = analyze(tmp_path)
    assert info.language == "python"
    assert all("node_modules" not in f for f in info.files)


def test_not_a_directory(tmp_path):
    with pytest.raises(NotADirectoryError):
        analyze(tmp_path / "missing")
