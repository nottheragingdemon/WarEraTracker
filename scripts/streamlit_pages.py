"""Build the pages the way the Streamlit app serves them (data inlined), without starting Streamlit.

    from streamlit_pages import build; html = build("index.html")
"""
import json, os, pathlib, re, types

ROOT = pathlib.Path(__file__).resolve().parent.parent


def build(name, root=ROOT):
    src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    start = re.search(r"@st\.cache_data\(ttl=\d+\)\ndef page", src).start()
    end = src.index("def show(")
    ns = {"st": types.SimpleNamespace(cache_data=lambda **kw: (lambda f: f)), "json": json, "re": re, "HERE": pathlib.Path(root)}
    exec(src[start:end], ns)
    return ns["page"](name)
