"""Streamlit web UI for dockergen.

Run from the project root:  streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from dockergen import validator
from dockergen.analyzer import analyze
from dockergen.generator import DEFAULT_MODEL, DockerfileGenerator

EXAMPLES_DIR = Path(__file__).parent / "examples"

st.set_page_config(page_title="dockergen", page_icon="🐳", layout="wide")


@st.cache_data(ttl=30, show_spinner=False)
def installed_models(host: str | None) -> list[str]:
    """Models already pulled into Ollama, or [] if Ollama isn't reachable."""
    try:
        import ollama

        client = ollama.Client(host=host) if host else ollama.Client()
        resp = client.list()
    except Exception:
        return []
    models = resp.get("models", []) if isinstance(resp, dict) else resp.models
    names = []
    for m in models:
        name = m.get("model") or m.get("name") if isinstance(m, dict) else m.model
        if name:
            names.append(name)
    return sorted(names)


@st.cache_data(ttl=30, show_spinner=False)
def docker_ok() -> bool:
    return validator.docker_available()


def show_dockerfile(text: str) -> None:
    st.code(text, language="docker", line_numbers=True)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
    host = st.text_input("Ollama host", placeholder="http://localhost:11434").strip() or None

    models = installed_models(host)
    if models:
        default_idx = models.index(DEFAULT_MODEL) if DEFAULT_MODEL in models else 0
        model = st.selectbox("Model", models, index=default_idx)
        st.caption("✅ Ollama is running")
    else:
        st.warning("Can't reach Ollama. Start it with `ollama serve`.")
        model = st.text_input("Model", value=DEFAULT_MODEL)
    custom = st.text_input("…or another model",
                           placeholder="hf.co/<user>/<repo>:<quant>",
                           help="Must already be pulled with `ollama pull`.").strip()
    if custom:
        model = custom

    st.divider()
    do_build = st.toggle("Build with Docker and auto-repair", value=False,
                         help="Runs `docker build`; failures go back to the model to fix.")
    retries = st.number_input("Max repair attempts", 0, 5, 2, disabled=not do_build)
    tag = st.text_input("Image tag", "dockergen-test", disabled=not do_build)
    if do_build and not docker_ok():
        st.error("Docker isn't available. Start Docker Desktop.")

# ---------------------------------------------------------------- main
st.title("🐳 dockergen")
st.write("Generate a Dockerfile for a project with a local LLM running in Ollama.")

examples = sorted(p.name for p in EXAMPLES_DIR.iterdir() if p.is_dir()) if EXAMPLES_DIR.is_dir() else []
col1, col2 = st.columns([1, 2])
with col1:
    example = st.selectbox("Example project", ["(none)"] + examples)
with col2:
    default_path = str(EXAMPLES_DIR / example) if example != "(none)" else ""
    path = st.text_input("Project folder", value=default_path,
                         placeholder=r"C:\path\to\your\project").strip()

if not path:
    st.info("Pick an example or enter the path to a project folder.")
    st.stop()

try:
    info = analyze(path)
except (NotADirectoryError, FileNotFoundError) as e:
    st.error(str(e))
    st.stop()

with st.expander(f"Project analysis: {info.root.name}", expanded=True):
    c = st.columns(4)
    c[0].metric("Language", info.language)
    c[1].metric("Entrypoint", info.entrypoint or "unknown")
    c[2].metric("Ports", ", ".join(map(str, info.ports)) or "none")
    c[3].metric("Files", len(info.files))
    st.caption("Marker files: " + (", ".join(info.marker_files) or "none"))

out = info.root / "Dockerfile"
save = st.checkbox(f"Save to `{out}`", value=True)
if save and out.exists():
    st.caption("⚠️ An existing Dockerfile there will be overwritten.")

if st.button("Generate Dockerfile", type="primary"):
    st.session_state.pop("result", None)
    try:
        gen = DockerfileGenerator(model=model, host=host)
        with st.spinner(f"Asking {model} for a Dockerfile…"):
            dockerfile = gen.generate(info)
    except Exception as e:
        st.error(f"Generation failed: {e}")
        st.caption(f"Is Ollama running? Try `ollama serve` and `ollama pull {model}`.")
        st.stop()

    attempts = [{"dockerfile": dockerfile, "build": None}]
    status = "generated"

    if do_build:
        if not docker_ok():
            st.error("Docker isn't available, so the build was skipped.")
        else:
            build_file = out if save else info.root / ".dockergen.Dockerfile"
            for attempt in range(int(retries) + 1):
                build_file.write_text(dockerfile, encoding="utf-8")
                with st.spinner(f"docker build (attempt {attempt + 1})…"):
                    result = validator.build(info.root, build_file, tag=tag)
                attempts[-1]["build"] = result
                if result.ok:
                    status = "built"
                    break
                status = "failed"
                if attempt == retries:
                    break
                try:
                    with st.spinner("Asking the model to fix the Dockerfile…"):
                        dockerfile = gen.repair(dockerfile, result.output)
                except Exception as e:
                    st.error(f"Repair failed: {e}")
                    break
                attempts.append({"dockerfile": dockerfile, "build": None})
            if not save:
                build_file.unlink(missing_ok=True)

    if save:
        out.write_text(dockerfile, encoding="utf-8")
    st.session_state.result = {"attempts": attempts, "status": status,
                               "final": dockerfile, "saved": save, "tag": tag,
                               "ports": info.ports, "model": model}

# ---------------------------------------------------------------- results
res = st.session_state.get("result")
if res:
    if res["status"] == "built":
        st.success(f"Build succeeded! Image tag: `{res['tag']}`")
        port = res["ports"][0] if res["ports"] else None
        st.code(f"docker run --rm -p {port}:{port} {res['tag']}" if port
                else f"docker run --rm {res['tag']}", language="powershell")
    elif res["status"] == "failed":
        st.error("Could not produce a building Dockerfile. Try a larger model, "
                 "e.g. `qwen2.5-coder:7b`.")

    st.subheader("Dockerfile")
    show_dockerfile(res["final"])
    st.download_button("Download Dockerfile", res["final"], file_name="Dockerfile")
    if res["saved"]:
        st.caption(f"Saved to `{out}`")

    if len(res["attempts"]) > 1 or res["attempts"][0]["build"]:
        st.subheader("Build attempts")
        for i, a in enumerate(res["attempts"], 1):
            b = a["build"]
            label = "✅ passed" if b and b.ok else "❌ failed" if b else "not built"
            with st.expander(f"Attempt {i}: {label}", expanded=False):
                show_dockerfile(a["dockerfile"])
                if b:
                    st.text("docker build output (last 3000 chars):")
                    st.code(b.output[-3000:], language="text")
