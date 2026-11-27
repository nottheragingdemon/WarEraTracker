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


@st.cache_data(ttl=3600)
def page(name: str, stamp: float = 0.0) -> str:   # stamp: the data file's modification time, so a new data commit gets fresh pages at once
    html = (HERE / "site" / name).read_text(encoding="utf-8")
    data = (HERE / "site" / "data.json").read_text(encoding="utf-8")
    loaded = json.loads(data)  # fail early if the file is damaged
    if name == "guide.html":   # the guide only shows the "Updated" stamp and the version check: it needn't carry the whole data file
        data = json.dumps({"schema": loaded.get("schema"), "generated": loaded.get("generated")})
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
    # pages that load an optional part of the data with weLoad(d, "file.json", [...]) get it inlined: the page runs from a string, so it can't fetch it
    parts = {}
    for part_name in ("battle-data.json", "transfer-data.json"):
        if 'weLoad(d,"' + part_name + '"' in html:
            part = (HERE / "site" / part_name).read_text(encoding="utf-8")
            json.loads(part)
            parts[part_name] = part
    if parts:
        files = "{" + ",".join(json.dumps(k) + ":" + v.replace("</", "<\\/") for k, v in parts.items()) + "}"
        html = html.replace("<script>" + js + "</script>", "<script>window.WE_FILES=" + files + ";</script><script>" + js + "</script>", 1)
    return html


def show(name: str):
    try:
        html = page(name, (HERE / "site" / "data.json").stat().st_mtime)   # our own pages and data, never user input
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


REPO = "nottheragingdemon/WarEraTracker-backend"   # the private back end holds agreements.json
AGREEMENTS_PATH = "agreements.json"
ALLIANCE = "The Emerald Accord"


def _gh(method, path, body=None):
    """GitHub contents API with the GITHUB_TOKEN from the app's Secrets (a fine-grained token: this repo, Contents read and write)."""
    import urllib.request
    token = str(st.secrets["GITHUB_TOKEN"])
    req = urllib.request.Request(f"https://api.github.com/repos/{st.secrets.get('GITHUB_REPO', REPO)}/contents/{path}",
                                 data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "warera-ireland-tools"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _gh_actions(method, path, body=None):
    """GitHub Actions API for the back-end repo (needs the token to have Actions: read and write)."""
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{st.secrets.get('GITHUB_REPO', REPO)}/actions/{path}",
                                 data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {str(st.secrets['GITHUB_TOKEN'])}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "warera-ireland-tools"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else {}


def _gh_repo(method, subpath, body=None):
    """Any GitHub REST path under the back-end repository (commits, contents at a version)."""
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{st.secrets.get('GITHUB_REPO', REPO)}/{subpath}",
                                 data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {str(st.secrets['GITHUB_TOKEN'])}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "warera-ireland-tools"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def history_panel(current_sha):
    """The last few saves of agreements.json, each restorable (a restore is a new save, so it can be undone too)."""
    import base64
    with st.expander("Earlier versions: undo a change"):
        try:
            commits = _gh_repo("GET", f"commits?path={AGREEMENTS_PATH}&per_page=6")
        except Exception as e:   # noqa: BLE001
            st.caption("Couldn't read the history. " + explain_save_error(e))
            return
        if not commits:
            st.caption("No earlier versions.")
        for i, c in enumerate(commits):
            when = c["commit"]["committer"]["date"][:16].replace("T", " ")
            msg = c["commit"]["message"].splitlines()[0]
            st.write(f"**{when} UTC**: {msg}" + (" (current)" if i == 0 else ""))
            if i and st.button("Restore this version", key=f"restore_{c['sha'][:10]}"):
                try:
                    old = _gh_repo("GET", f"contents/{AGREEMENTS_PATH}?ref={c['sha']}")
                    _gh_repo("PUT", f"contents/{AGREEMENTS_PATH}", {"message": f"Settings: restored the version of {when} (from the Streamlit app)",
                                                                      "content": old["content"].replace("\n", ""), "sha": current_sha})
                    st.success("Restored. Reload the page to see it; the collector uses it from the next hourly refresh.")
                except Exception as e:   # noqa: BLE001
                    st.error("Couldn't restore it. " + explain_save_error(e))


def dryrun_panel():
    """Latest month-end dry run, and a button to start one (the check runs on GitHub against a copy of the history; nothing real changes)."""
    import base64
    with st.expander("Month-end check: will next month's statement come out right?"):
        st.caption("Saves this month's statement on a copy of the history, as if the month had just ended, and checks the figures, the paper price "
                   "and the CSV. It also runs by itself on 30 November. Nothing real is changed.")
        try:
            runs = _gh_actions("GET", "workflows/month-dryrun.yml/runs?per_page=1").get("workflow_runs") or []
            if runs:
                r = runs[0]
                state = r["conclusion"] or r["status"]
                {"success": st.success, "failure": st.error}.get(state, st.info)(f"Latest check: {state} ({r['created_at'][:16].replace('T', ' ')} UTC).")
                st.link_button("See the details on GitHub", r["html_url"])
            else:
                st.caption("No check has run yet.")
        except Exception as e:   # noqa: BLE001
            st.caption("Couldn't read the latest check. " + explain_actions_error(e))
        try:   # what the last check looked at, in plain words (the workflow saves it as dryrun-result.json in the back-end repo)
            got = _gh("GET", "dryrun-result.json")
            res = json.loads(base64.b64decode(got["content"]).decode())
            st.write(f"**Last result ({res.get('at', '?')}):** " + ("nothing wrong found." if res.get("ok") else "a problem was found."))
            for line in res.get("checked") or []:
                st.write("• " + line)
            for line in res.get("problems") or []:
                st.error(line)
        except Exception:   # noqa: BLE001  no result saved yet
            pass
        if st.button("Run the check now", key="dryrun_go"):
            try:
                _gh_actions("POST", "workflows/month-dryrun.yml/dispatches", {"ref": "main"})
                st.success("Started. It takes about a minute; reopen this section to see the result.")
            except Exception as e:   # noqa: BLE001
                st.error("Couldn't start it. " + explain_actions_error(e))


def explain_actions_error(e):
    import urllib.error
    if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404):
        return "The app's GitHub token needs the Actions permission (read and write) on the back-end repository for this."
    return explain_save_error(e)


def explain_save_error(e):
    """A plain-language reason for a failed save (GitHub's raw error text means little on a phone)."""
    import urllib.error
    code = e.code if isinstance(e, urllib.error.HTTPError) else None
    if code == 401:
        return "GitHub didn't accept the token (it may have expired). Make a new fine-grained token and put it in this app's Secrets as GITHUB_TOKEN."
    if code == 403:
        return "The token isn't allowed to write to the back-end repository. It needs Contents: read and write on that repo (or GitHub is rate-limiting; try again in a minute)."
    if code == 404:
        return "GitHub can't find agreements.json or the repository for this token. Check GITHUB_REPO and that the token covers the back-end repo."
    if code in (409, 422):
        return "Someone saved a change while this page was open. Reload the page to get the latest list, then make your change again."
    if code and code >= 500:
        return "GitHub is having problems. Nothing was saved; try again shortly."
    if isinstance(e, (urllib.error.URLError, TimeoutError)):
        return "Couldn't reach GitHub. Nothing was saved; check the connection and try again."
    return f"{e}"


def token_status():
    """('ok'|'warn'|'bad', message) for the Settings token: GitHub reports a fine-grained token's expiry in a response header."""
    import datetime as dt, urllib.error, urllib.request
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{st.secrets.get('GITHUB_REPO', REPO)}", headers={
            "Authorization": f"Bearer {st.secrets['GITHUB_TOKEN']}", "User-Agent": "warera-ireland-tools"})
        with urllib.request.urlopen(req, timeout=20) as r:
            exp = r.headers.get("github-authentication-token-expiration")
    except urllib.error.HTTPError as e:
        return "bad", f"GitHub rejected the token (HTTP {e.code}). It has expired or can't reach the back-end repository."
    except Exception as e:
        return "bad", f"Couldn't check the token: {e}"
    missing = []   # what the token can't read (GitHub doesn't list a token's permissions; a read tells whether the permission is there)
    for label, probe in (("Contents (the agreements file)", lambda: _gh("GET", AGREEMENTS_PATH)),
                         ("Actions (the month-end check button)", lambda: _gh_actions("GET", "workflows"))):
        try:
            probe()
        except Exception:   # noqa: BLE001
            missing.append(label)
    extra = f" Missing permission: {', '.join(missing)}." if missing else ""
    if not exp:
        return ("warn" if missing else "ok"), "Token works (no expiry date)." + extra
    left = (dt.datetime.strptime(exp.replace(" UTC", "").strip(), "%Y-%m-%d %H:%M:%S") - dt.datetime.utcnow()).days
    return ("warn" if left < 14 or missing else "ok"), f"Token works and expires {exp[:10]} ({left} days left)." + extra


@st.cache_data(ttl=300, show_spinner=False)
def token_status_cached():
    return token_status()


def _has_token():
    try:
        return bool(st.secrets["GITHUB_TOKEN"])
    except Exception:
        return False


def preview_changes(data, current, new):
    """Plain-language lines for what a Settings change would do, using the latest month's tracked tax (rates only; a change of
    regions or start date alters what is collected, which can't be estimated from existing data)."""
    ents = data.get("ents", [])
    ids = {e[2]: i for i, e in enumerate(ents) if e[0] == "country" and e[2]}
    months = sorted(set((data.get("statementsLive") or {})) | set((data.get("statements") or {})))
    out = []
    def gen(host, partner, month):
        rows = ((data.get("statements") or {}).get(month, {}) or {}).get(str(ids.get(host))) or \
               ((data.get("statementsLive") or {}).get(month, {}) or {}).get(str(ids.get(host))) or []
        return next((r[1] for r in rows if r[0] == ids.get(partner)), None)
    for h in sorted(set(current) | set(new)):
        old = {x["country"]: x for x in current.get(h, [])}
        nw = {x["country"]: x for x in new.get(h, [])}
        for c in sorted(set(old) | set(nw)):
            if c not in nw:
                out.append(f"{h} ↔ {c}: agreement removed. {c}'s companies are no longer collected or billed.")
            elif c not in old:
                out.append(f"{h} ↔ {c}: new agreement ({nw[c]['pay_percent']}%, from {nw[c]['payments_since']}). Collection starts at the next refresh; there is no history before that.")
            else:
                a, b = old[c], nw[c]
                if a["pay_percent"] != b["pay_percent"]:
                    m = months[-1] if months else None
                    g = gen(h, c, m) if m else None
                    est = f" On {m}'s tracked tax ({g:,.2f}) that is {g * a['pay_percent'] / 100:,.2f} → {g * b['pay_percent'] / 100:,.2f}." if g else ""
                    out.append(f"{h} ↔ {c}: rate {a['pay_percent']}% → {b['pay_percent']}%.{est} Months already saved as final keep their old rate.")
                if a["regions"] != b["regions"]:
                    out.append(f"{h} ↔ {c}: regions covered change. Applies from the next refresh; saved months keep their old scope.")
                if a.get("payments_until") != b.get("payments_until"):
                    out.append(f"{h} ↔ {c}: end date {a.get('payments_until') or 'none'} → {b.get('payments_until') or 'none'}. After the last day's month is saved, the agreement drops out and its partner is no longer collected.")
                if a["payments_since"] != b["payments_since"]:
                    out.append(f"{h} ↔ {c}: start date {a['payments_since']} → {b['payments_since']}. Statements count from the new date.")
    return out


def settings():
    import base64
    st.title("⚙️ Settings")
    st.subheader("Tax agreements")
    st.caption("For each host country (where the companies stand): the partner countries whose citizens' companies are covered, and which "
               "regions each agreement covers. The host pays each partner the tax it collects on those companies. Only these companies "
               "are collected; changes apply from the next hourly refresh.")
    data = json.loads((HERE / "site" / "data.json").read_text(encoding="utf-8"))
    ents = data.get("ents", [])
    names = sorted({e[2] for e in ents if e[0] == "country" and e[2]})
    hosts = []
    for a, members in (data.get("alliances") or {}).items():
        if ents[int(a)][2] == ALLIANCE:
            hosts = sorted(ents[c][2] for c in members if ents[c][2])
    sha, current, cur_ratio = None, {}, float(data.get("paperRatio") or 0.5)
    if _has_token():   # checked when the page opens (kept for 5 minutes), so a dead token shows before anything is edited
        kind, msg = token_status_cached()
        {"ok": st.success, "warn": st.warning, "bad": st.error}[kind](msg)
        dryrun_panel()

    def published():   # the agreements as published in data.json (ids turned back into names); core regions show as the list of regions
        out = {}
        rn = {k: r[0] for k, r in (data.get("regionsNow") or {}).items()}
        def scope(h, ids):   # the published list of region ids back to "all" / "core" when it is exactly that
            if ids is None:
                return "all"
            ids = set(ids)
            mine = {k for k, r in (data.get("regionsNow") or {}).items() if r[1] == int(h)}
            core = {k for k in mine if len(data["regionsNow"][k]) > 6 and data["regionsNow"][k][6] == int(h)}
            if ids and ids == mine:
                return "all"
            if ids and ids == core:
                return "core"
            return [rn.get(r, r) for r in ids]
        for h, items in (data.get("agreements") or {}).items():
            out[ents[int(h)][2]] = [{"country": ents[x[0]][2], "regions": scope(h, x[1]),
                                     "pay_percent": x[2] if len(x) > 2 else 90, "payments_since": x[3] if len(x) > 3 else "2026-11-01"} for x in items]
        return out
    if _has_token():
        try:
            got = _gh("GET", AGREEMENTS_PATH)
            sha = got["sha"]
            _file = json.loads(base64.b64decode(got["content"]).decode())
            current = _file.get("agreements") or {}
            cur_ratio = float(_file.get("paper_ratio", 0.5))
            history_panel(sha)
        except Exception as e:   # the token can't read the file (GitHub answers 404 when a token has no access to a private repository)
            current = published()
            st.warning(f"Couldn't read agreements.json with this app's GitHub token. {explain_save_error(e)} The agreements shown are the ones published "
                       "on the pages. Saving is off until the token can read the file.")
            sha = "unreadable"
    else:
        current = published()
    regions_of = {}
    for _rid, r in (data.get("regionsNow") or {}).items():
        host_name = ents[r[1]][2] if r[1] is not None and r[1] >= 0 else None
        if host_name:
            regions_of.setdefault(host_name, []).append(r[0])
    def norm(items):   # [{"country", "regions"}], also accepting bare names
        return [{"country": x, "regions": "all", "pay_percent": 90, "payments_since": "2026-11-01"} if isinstance(x, str) else
                dict({"country": x.get("country"), "regions": x.get("regions", "all"), "pay_percent": x.get("pay_percent", 90),
                      "payments_since": x.get("payments_since", "2026-11-01")}, **({"payments_until": x["payments_until"]} if x.get("payments_until") else {})) for x in items or []]
    current = {h: norm(v) for h, v in current.items()}
    SCOPES = {"Core regions only (not conquered ones)": "core", "All regions": "all", "Chosen regions": "list"}
    new = {}
    for h in sorted(set(hosts) | set(current), key=lambda h: (not current.get(h), h)):   # countries with an agreement first
        cur = {x["country"]: x["regions"] for x in current.get(h, []) if x["country"]}
        cur_pay = {x["country"]: x["pay_percent"] for x in current.get(h, []) if x["country"]}
        cur_since = {x["country"]: x["payments_since"] for x in current.get(h, []) if x["country"]}
        cur_until = {x["country"]: x.get("payments_until") for x in current.get(h, []) if x["country"]}
        st.markdown(f"#### {h}")
        picked = st.multiselect(f"{h}: partner countries (whose citizens' companies are covered)", names,
                                default=[c for c in cur if c in names], key=f"ag_{h}", placeholder="no agreement")
        items = []
        for c in picked:
            with st.container(border=True):
                was = cur.get(c, "all")
                kind = "list" if isinstance(was, list) else was
                label = st.selectbox(f"{h} ↔ {c}: regions covered", list(SCOPES), key=f"sc_{h}_{c}",
                                     index=list(SCOPES.values()).index(kind if kind in SCOPES.values() else "all"))
                scope = SCOPES[label]
                if scope == "list":
                    opts = sorted(regions_of.get(h, []))
                    scope = st.multiselect(f"{h} ↔ {c}: which regions", opts, default=[r for r in (was if isinstance(was, list) else []) if r in opts], key=f"rg_{h}_{c}")
                pay = st.number_input(f"{h} ↔ {c}: % of the tax generated that {h} pays {c}", min_value=0.0, max_value=100.0, step=1.0,
                                      value=float(cur_pay.get(c, 90)), key=f"pp_{h}_{c}")
                import datetime as _dt
                since = st.date_input(f"{h} ↔ {c}: agreement start (statements count from)", key=f"sd_{h}_{c}",
                                      value=_dt.date.fromisoformat(str(cur_since.get(c, "2026-11-01"))))
                was_until = cur_until.get(c)
                ends = st.checkbox(f"{h} ↔ {c}: the agreement ends on a set date", value=bool(was_until), key=f"en_{h}_{c}")
                until = None
                if ends:
                    until = st.date_input(f"{h} ↔ {c}: last day (that month is the last one billed; the agreement then drops out)", key=f"ud_{h}_{c}",
                                          value=_dt.date.fromisoformat(str(was_until)) if was_until else since.replace(day=28)).isoformat()
                items.append(dict({"country": c, "regions": scope, "pay_percent": int(pay) if pay == int(pay) else pay, "payments_since": since.isoformat()},
                                  **({"payments_until": until} if until else {})))
        if items:
            new[h] = items
    if not new:
        st.warning("With no agreements at all, no company data is collected.")
    ratio = st.number_input("Paper needed to send a tax payment, per unit of tax", min_value=0.0, max_value=10.0, step=0.05, value=cur_ratio, key="paper_ratio",
                            help="Sending tax costs paper: the amount × this (now 0.5). The cost uses the market price of paper.")
    body = {"about": "Tax agreements. For each host country (where the companies stand): the partner countries whose citizens' companies are "
                     "covered, and which of the host's regions each agreement covers: \"all\", \"core\" (the host's own original regions, not "
                     "conquered ones) or a list of region names. The host sends the partner the tax it collects on those companies' employee "
                     "and manager wages (pay_percent of it). Only these companies are collected. Edited from the Streamlit Settings page.",
            "paper_ratio": ratio, "agreements": new}
    if not _has_token():
        st.info("Saving needs a GITHUB_TOKEN in this app's Secrets (a fine-grained token for the private WarEraTracker-backend repository "
                "with Contents: read and write). Until then, copy this into agreements.json in that repository:")
        st.code(json.dumps(body, indent=2), language="json")
        return
    if new == {h: v for h, v in current.items() if v} and abs(ratio - cur_ratio) < 1e-9:
        st.caption("No changes.")
        return
    if abs(ratio - cur_ratio) > 1e-9:
        st.write(f"• Paper per unit of tax {cur_ratio:g} → {ratio:g}. Applies to every month's paper figures at the next refresh.")
    for line in preview_changes(data, current, new):
        st.write("• " + line)
    if sha == "unreadable":
        return
    if st.button("Save agreements", type="primary"):
        try:
            payload = {"message": "Settings: tax agreements (from the Streamlit app)",
                       "content": base64.b64encode((json.dumps(body, indent=2) + "\n").encode()).decode()}
            if sha:
                payload["sha"] = sha
            _gh("PUT", AGREEMENTS_PATH, payload)
            st.success("Saved. The collector uses it from the next hourly refresh; the pages follow after that refresh.")
        except Exception as e:
            st.error(f"Couldn't save. {explain_save_error(e)} What you typed is still here; nothing was changed.")


# Temporarily hidden while testing. Open the app with ?key=<DEV_KEY> (DEV_KEY is set in the app's Secrets, never in the repo)
# to see them; the unlock lasts for that browser session. Set HIDDEN = () to bring the pages back for everyone.
HIDDEN = ("ask", "settings")


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
    "settings": st.Page(settings, title="Settings", icon="⚙️", url_path="settings"),
}
_dev = _unlocked()
SHORT = {"tracker": "Tracker", "company-tax": "Taxes", "transfers": "Transfers", "efficiency": "Efficiency",
         "status": "Status", "guide": "Guide", "ask": "Ask", "settings": "Settings"}
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
