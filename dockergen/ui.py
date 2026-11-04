"""`dockergen-ui` command: launch the Streamlit web UI."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        print("The web UI needs Streamlit. Install it with:\n"
              '  pip install "llm-dockerfile-generator[ui]"', file=sys.stderr)
        return 1
    sys.argv = ["streamlit", "run", str(Path(__file__).with_name("webui.py")), *sys.argv[1:]]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
