"""WarEra apps: the war tracker dashboard and the Company tax tracker, each with the latest site/data.json inlined."""
import hmac
import json
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
st.set_page_config(page_title="WarEra", page_icon="⚔️", layout="wide")
st.markdown("<style>[data-testid=\"stMainBlockContainer\"],.block-container{padding:4.5rem 0.5rem 0 !important}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def page(name: str) -> str:
    html = (HERE / "site" / name).read_text(encoding="utf-8")
    data = (HERE / "site" / "data.json").read_text(encoding="utf-8")
    json.loads(data)  # fail early if the file is damaged
    old = 'fetch("data.json").then(function(r){return r.json()})'
    if old not in html:
        raise RuntimeError(f"{name} no longer loads data.json the expected way")
    html = re.sub(r'<nav class="apps" id="apps">.*?</nav>', "", html, flags=re.S)  # Streamlit's own navigation replaces it
    css = (HERE / "site" / "theme.css").read_text(encoding="utf-8")
    js = (HERE / "site" / "theme.js").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="theme.css">', "<style>" + css + "</style>")
    html = html.replace('<script src="theme.js"></script>', "<script>" + js + "</script>")
    html = html.replace(old, "Promise.resolve(" + data.replace("</", "<\\/") + ")", 1)
    extra_fetch = 'fetch("ask-data.json").then(function(r){return r.json()})'
    if extra_fetch in html:   # the Ask page also needs bounty history and contracts
        extra = (HERE / "site" / "ask-data.json").read_text(encoding="utf-8")
        json.loads(extra)
        html = html.replace(extra_fetch, "Promise.resolve(" + extra.replace("</", "<\\/") + ")", 1)
    return html


def show(name: str):
    try:
        html = page(name)   # our own pages and data, never user input
        if hasattr(st, "iframe"):   # components.html is deprecated in newer Streamlit
            st.iframe(html, height=1600)
        else:
            components.html(html, height=1600, scrolling=True)
    except FileNotFoundError:
        st.error("site/data.json not found yet. Run the “Refresh data” workflow once.")


def tracker():
    show("index.html")


def company_tax():
    show("company.html")


def transfers():
    show("transfers.html")


ASK_URL = "https://claude.ai/artifact/QyeXBuXu5Sksfsdeco8Dhx"


def ask_warera():
    st.header("Ask WarEra")
    st.write(
        "Type a question in plain English and Claude queries the tracker data (and, for live facts, the WarEra API) "
        "and returns a table. It runs inside Claude, using your own Claude account, so access is controlled by who the "
        "page is shared with in Claude."
    )
    st.link_button("Open Ask WarEra", ASK_URL.rstrip("/"), type="primary")


# Temporarily hidden while testing. Open the app with ?key=<DEV_KEY> (DEV_KEY is set in the app's Secrets, never in the repo)
# to see them; the unlock lasts for that browser session. Set HIDDEN = () to bring the pages back for everyone.
HIDDEN = ("ask",)


def _unlocked():
    if st.session_state.get("dev_ok"):
        return True
    try:
        secret = str(st.secrets["DEV_KEY"])
    except Exception:  # no secret configured: nobody is unlocked
        return False
    given = st.query_params.get("key", "")
    if secret and hmac.compare_digest(str(given).encode(), secret.encode()):
        st.session_state["dev_ok"] = True
        return True
    return False


_pages = {
    "tracker": st.Page(tracker, title="WarEra Tracker", icon="⚔️", url_path="tracker", default=True),
    "company-tax": st.Page(company_tax, title="Company tax tracker", icon="🏭", url_path="company-tax"),
    "transfers": st.Page(transfers, title="EA Money Transfers", icon="💸", url_path="transfers"),
    "ask": st.Page(ask_warera, title="Ask WarEra", icon="💬", url_path="ask"),
}
_dev = _unlocked()
nav = st.navigation([pg for key, pg in _pages.items() if _dev or key not in HIDDEN], position="top")
st.markdown(
    '<div style="text-align:right;font-size:14px"><a href="https://we.hawtre.net/" target="_blank" rel="noopener noreferrer">we.hawtre.net ↗</a></div>',
    unsafe_allow_html=True,
)
nav.run()
