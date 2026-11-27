"""WarEra apps: the war tracker dashboard and the Company tax tracker, each with the latest site/data.json inlined."""
import hmac
import json
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
st.set_page_config(page_title="WarEra Ireland tools", page_icon="⚔️", layout="wide")
# No Streamlit top bar or sidebar: a fixed menu at the top switches apps.
st.markdown("""<style>
header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stToolbarActions"],[data-testid="stAppDeployButton"],[data-testid="stMainMenu"],[class*="viewerBadge"],[class*="profileContainer"],[class*="profilePreview"],[data-testid="appCreatorAvatar"],a[href*="github.com"],.st-key-ghhide,[data-testid="stDecoration"],[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"]{display:none !important}
[data-testid="stMainBlockContainer"],.block-container{padding:3.4rem 0.5rem 0.5rem !important}
[data-testid="stElementContainer"]:has(>[data-testid="stMarkdown"] style),[data-testid="stElementContainer"]:has(style:only-child){display:none}
[data-testid="stLayoutWrapper"]:has(>.st-key-appnav){display:contents}
[data-testid="stLayoutWrapper"]:has(>.st-key-ghhide),[data-testid="stElementContainer"]:has(>.st-key-ghhide){display:none !important}
.st-key-appnav{position:fixed;left:0;right:0;top:0;z-index:1000;background:#14181d;border-bottom:1px solid #2a313a;padding:calc(6px + env(safe-area-inset-top)) 6px 6px;
  display:flex !important;flex-direction:row !important;flex-wrap:nowrap !important;gap:2px !important;overflow-x:auto;justify-content:safe center;scrollbar-width:none}
.st-key-appnav::-webkit-scrollbar{display:none}
.st-key-appnav>div{flex:0 0 auto !important;width:auto !important;min-width:0 !important}
.st-key-appnav a{display:flex !important;flex-direction:column;align-items:center;gap:1px;padding:4px 10px !important;border-radius:10px;text-decoration:none !important;min-width:58px}
.st-key-appnav a p{font-size:11px !important;line-height:1.2;margin:0;white-space:nowrap}
.st-key-appnav a span[data-testid="stIconEmoji"],.st-key-appnav a span:first-child{font-size:20px !important;line-height:1.1;margin:0 !important}
.st-key-appnav .wenavsec{display:flex;align-items:center;height:100%;padding:0 4px 0 10px;margin-left:4px;border-left:1px solid #2a313a;color:#9aa4b2;font-size:10px;letter-spacing:.06em;text-transform:uppercase}
.st-key-appnav [data-testid="stMarkdownContainer"] p{margin:0}
.st-key-appnav a[aria-current="page"],.st-key-appnav a[data-testid*="Active"],.st-key-appnav a.active{background:rgba(74,222,128,0.14)}
</style>""", unsafe_allow_html=True)


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
    for extra_name in ("ask-data.json", "company-data.json"):   # pages that load a second data file get it inlined too
        extra_fetch = 'fetch("' + extra_name + '").then(function(r){return r.json()})'
        if extra_fetch in html:
            extra = (HERE / "site" / extra_name).read_text(encoding="utf-8")
            json.loads(extra)
            html = html.replace(extra_fetch, "Promise.resolve(" + extra.replace("</", "<\\/") + ")", 1)
    return html


def show(name: str):
    try:
        html = page(name)   # our own pages and data, never user input
        if hasattr(st, "iframe"):   # components.html is deprecated in newer Streamlit
            st.iframe(html, height="content")
        else:
            components.html(html, height=1600, scrolling=True)
    except FileNotFoundError:
        st.error("site/data.json not found yet. Run the “Refresh data” workflow once.")


def guide():
    show("guide.html")


def status():
    show("status.html")


def efficiency():
    show("efficiency.html")


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
    "efficiency": st.Page(efficiency, title="Player efficiency", icon="⚖️", url_path="efficiency"),
    "status": st.Page(status, title="Status", icon="🩺", url_path="status"),
    "guide": st.Page(guide, title="Guide", icon="📖", url_path="guide"),
    "ask": st.Page(ask_warera, title="Ask WarEra", icon="💬", url_path="ask"),
}
_dev = _unlocked()
SHORT = {"tracker": "Tracker", "company-tax": "Taxes", "transfers": "Transfers", "efficiency": "Efficiency",
         "status": "Status", "guide": "Guide", "ask": "Ask"}
_shown = [(key, pg) for key, pg in _pages.items() if _dev or key not in HIDDEN]
nav = st.navigation([pg for _, pg in _shown], position="hidden")
with st.container(key="appnav"):   # the app menu: one button per app (styled fixed at the top above)
    for key, pg in _shown:
        st.page_link(pg, label=SHORT[key], icon=pg.icon)
    st.page_link("https://we.hawtre.net/", label="we.hawtre", icon="↗️")
    st.markdown('<span class="wenavsec">Games</span>', unsafe_allow_html=True)   # the Games section: links to web games
    st.page_link("https://maptap.gg/", label="MapTap", icon="🎮")
    st.page_link("https://boreen.ie/", label="Boreen", icon="🎮")
# Streamlit Community Cloud adds GitHub links (Fork / GitHub buttons, the creator's GitHub avatar badge) to the page around
# the app. That page is on the same origin, so a tiny script hides them there too; the CSS above covers the app's own copy.
_HIDE_GH = """<script>(function(){var css='a[href*="github.com"],[class*="viewerBadge"],[class*="profileContainer"],[class*="profilePreview"],'+
'[data-testid="appCreatorAvatar"],[data-testid="stToolbarActions"],[data-testid="stAppDeployButton"]{display:none !important}';
var w=window;for(var i=0;i<4&&w;i++){try{var d=w.document;if(!d.getElementById('we-hide-gh')){var s=d.createElement('style');s.id='we-hide-gh';
s.textContent=css;d.head.appendChild(s)}}catch(e){}if(w===w.parent)break;w=w.parent}})();</script>"""
with st.container(key="ghhide"):
    if hasattr(st, "iframe"):   # components.html is deprecated in newer Streamlit
        st.iframe(_HIDE_GH, height=1)
    else:
        components.html(_HIDE_GH, height=0)
nav.run()
