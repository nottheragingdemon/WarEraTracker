#!/usr/bin/env python3
"""Build the two Claude-artifact copies of the site from site/ (one source of truth, so the copies cannot drift).

    python3 scripts/sync_artifacts.py OUT_DIR

Writes OUT_DIR/tracker/ (Tracker, Company tax tracker, EA Money Transfers, Player efficiency) and OUT_DIR/ask/ (Ask WarEra as its own artifact).
Only two things differ from site/: the Ask link in the Tracker's navigation points at the Ask artifact (shown in testing mode only),
and the Ask artifact's navigation has just itself. Prints the artifact file lists as JSON for the publishing step.
"""
import json, os, re, shutil, sys

SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site")
ASK_URL = "https://claude.ai/artifact/QyeXBuXu5Sksfsdeco8Dhx"
ASK_LINK = f'<a href="{ASK_URL}" target="_blank" rel="noopener noreferrer" class="ext" data-dev>Ask WarEra ↗</a>'
ASK_NAV = ('<nav class="apps" id="apps"><a href="index.html" aria-current="page">Ask WarEra</a>'
           '<a href="https://we.hawtre.net/" target="_blank" rel="noopener noreferrer" class="ext">we.hawtre.net ↗</a><span class="navsec" aria-hidden="true">Games</span><a href="https://maptap.gg/" target="_blank" rel="noopener noreferrer" class="game" aria-label="Games: MapTap">MapTap ↗</a><a href="https://boreen.ie/" target="_blank" rel="noopener noreferrer" class="game" aria-label="Games: Boreen">Boreen ↗</a></nav>')


def read(name):
    with open(os.path.join(SITE, name), encoding="utf-8") as f:
        return f.read()


def write(folder, name, text):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)


def build(out):
    tracker, ask = os.path.join(out, "tracker"), os.path.join(out, "ask")
    for d in (tracker, ask):
        shutil.rmtree(d, ignore_errors=True)
    link = '<a href="ask.html">Ask WarEra</a>'
    for name in ("index.html", "company.html", "transfers.html", "efficiency.html", "status.html", "guide.html"):
        html = read(name)
        if link not in html:
            raise SystemExit(f"{name}: the Ask link in the navigation was not found")
        write(tracker, name, html.replace(link, ASK_LINK))
    page, n = re.subn(r'<nav class="apps" id="apps">.*?</nav>', ASK_NAV, read("ask.html"), count=1, flags=re.S)
    if n != 1:
        raise SystemExit("ask.html: navigation not found")
    write(ask, "index.html", page)
    for name in ("theme.js", "theme.css", "data.json", "company-data.json", "battle-data.json", "transfer-data.json", "enemy-data.json"):
        if name == "enemy-data.json" and not os.path.exists(os.path.join(SITE, name)):
            continue   # not published yet
        write(tracker, name, read(name))
    for name in ("theme.js", "theme.css", "data.json", "ask-data.json", "company-data.json", "battle-data.json"):
        write(ask, name, read(name))
    return {"tracker": sorted(os.listdir(tracker)), "ask": sorted(os.listdir(ask)),
            "generated": json.loads(read("data.json"))["generated"]}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(json.dumps(build(sys.argv[1]), indent=1))
