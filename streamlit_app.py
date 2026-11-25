"""WarEra apps: the war tracker dashboard and the Company tax tracker, each with the latest site/data.json inlined."""
import json
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
st.set_page_config(page_title="WarEra", page_icon="⚔️", layout="wide")
st.markdown("<style>.block-container{padding:0.5rem 0.5rem 0}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def page(name: str) -> str:
    html = (HERE / "site" / name).read_text(encoding="utf-8")
    data = (HERE / "site" / "data.json").read_text(encoding="utf-8")
    json.loads(data)  # fail early if the file is damaged
    old = 'fetch("data.json").then(function(r){return r.json()})'
    if old not in html:
        raise RuntimeError(f"{name} no longer loads data.json the expected way")
    html = re.sub(r'<nav class="apps" id="apps">.*?</nav>', "", html, flags=re.S)  # Streamlit's own navigation replaces it
    return html.replace(old, "Promise.resolve(" + data.replace("</", "<\\/") + ")", 1)


def show(name: str):
    try:
        components.html(page(name), height=1600, scrolling=True)
    except FileNotFoundError:
        st.error("site/data.json not found yet. Run the “Refresh data” workflow once.")


def tracker():
    show("index.html")


def company_tax():
    show("company.html")


ASK_URL = "https://claude.ai/artifact/JaT33Me1TK4kUoGEXjJKZg"


def ask_claude():
    st.header("Ask Claude about WarEra")
    st.write(
        "Type a question in plain English and Claude queries the tracker data (and, for live facts, the WarEra API) "
        "and returns a table. It runs inside Claude, using your own Claude account, so access is controlled by who the "
        "page is shared with in Claude."
    )
    st.link_button("Open Ask Claude", ASK_URL.rstrip("/"), type="primary")


nav = st.navigation(
    [
        st.Page(tracker, title="WarEra Tracker", icon="⚔️", url_path="tracker", default=True),
        st.Page(company_tax, title="Company tax tracker", icon="🏭", url_path="company-tax"),
        st.Page(ask_claude, title="Ask Claude", icon="💬", url_path="ask"),
    ],
    position="top",
)
nav.run()
