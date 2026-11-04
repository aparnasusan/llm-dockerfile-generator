"""Run the web UI from a source checkout: streamlit run app.py

The UI itself lives in dockergen/webui.py. run_module re-executes it on every Streamlit
rerun (a plain import would only run it once).
"""

import runpy

runpy.run_module("dockergen.webui", run_name="__main__")
