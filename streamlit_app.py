"""WarEra Tracker: serves the dashboard (site/index.html) with the latest site/data.json inlined."""
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
st.set_page_config(page_title="WarEra Tracker", page_icon="⚔️", layout="wide")
st.markdown("<style>.block-container{padding:0.5rem 0.5rem 0} header{display:none}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def page() -> str:
    html = (HERE / "site" / "index.html").read_text(encoding="utf-8")
    data = (HERE / "site" / "data.json").read_text(encoding="utf-8")
    json.loads(data)  # fail early if the file is damaged
    old = 'fetch("data.json").then(function(r){return r.json()})'
    if old not in html:
        raise RuntimeError("dashboard no longer loads data.json the expected way")
    return html.replace(old, "Promise.resolve(" + data.replace("</", "<\\/") + ")", 1)


try:
    components.html(page(), height=1500, scrolling=True)
except FileNotFoundError:
    st.error("site/data.json not found yet. Run the “Refresh data” workflow once.")
