#!/usr/bin/env python3
"""Accessibility check of every page (axe-core in headless Chrome), in the light and the dark theme.

    AXE=/path/to/axe.min.js python3 scripts/a11y_pages.py [chrome binary]

Fails on the problems that stop someone using a page: text that is hard to read (colour contrast), buttons, links and form fields with no
name, images with no description. Install axe with: npm install axe-core (the file is node_modules/axe-core/axe.min.js).
"""
import http.server, json, os, re, shutil, subprocess, sys, tempfile, threading

SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site")
PAGES = ["index.html", "company.html", "transfers.html", "efficiency.html", "status.html", "guide.html"]
RULES = ["color-contrast", "button-name", "link-name", "label", "image-alt", "select-name", "aria-valid-attr-value"]
PROBE = """<script src="axe.min.js"></script><script>window.__ax=null;
try{localStorage.setItem("we-dev","1")}catch(e){}
setTimeout(function(){
 axe.run(document,{runOnly:{type:"rule",values:%s}}).then(function(r){document.body.setAttribute("data-axe",JSON.stringify(r.violations.map(function(v){return{id:v.id,n:v.nodes.length,t:v.nodes.slice(0,3).map(function(n){return n.target.join(" ")+" :: "+((n.any[0]||n.all[0]||n.none[0]||{}).message||"")})}})))})},5000)</script>"""


def main(chrome, axe):
    bad = []
    for theme in ("light", "dark"):
        tmp = tempfile.mkdtemp()
        for f in os.listdir(SITE):
            if os.path.isfile(os.path.join(SITE, f)):
                shutil.copy(os.path.join(SITE, f), tmp)
        shutil.copy(axe, os.path.join(tmp, "axe.min.js"))
        for p in PAGES:
            path = os.path.join(tmp, p)
            html = open(path, encoding="utf-8").read()
            open(path, "w", encoding="utf-8").write(html.replace("<head>", "<head>" + PROBE % json.dumps(RULES), 1))
        http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=tmp))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        for p in PAGES:
            dom = subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--blink-settings=preferredColorScheme=" + ("0" if theme == "dark" else "1"), "--virtual-time-budget=12000", "--dump-dom",
                                  f"http://127.0.0.1:{srv.server_address[1]}/{p}"], capture_output=True, text=True, timeout=120).stdout
            m = re.search(r'data-axe="([^"]*)"', dom)
            if not m:
                print(f"FAIL {p} ({theme}): axe did not run"); bad.append(p); continue
            v = json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))
            print(f"{'ok  ' if not v else 'FAIL'} {p} ({theme}): " + (", ".join(f"{x['id']} x{x['n']}" for x in v) or "no problems"))
            for x in v:
                for t in x["t"]:
                    print("      ", x["id"], t[:160])
            if v:
                bad.append(f"{p} ({theme})")
        srv.shutdown(); shutil.rmtree(tmp)
    if bad:
        raise SystemExit("accessibility problems: " + ", ".join(bad))


if __name__ == "__main__":
    ax = os.environ.get("AXE") or "node_modules/axe-core/axe.min.js"
    main(shutil.which("google-chrome") or shutil.which("chromium") or "google-chrome", ax)
