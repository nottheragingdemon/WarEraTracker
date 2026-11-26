#!/usr/bin/env python3
"""Open every page of site/ in headless Chrome and fail if one throws a JavaScript error or does not load its data.

    python3 scripts/smoke_pages.py [chrome binary]

Each page is served from a temporary copy with a small probe added: it records uncaught errors, turns on testing mode
(so hidden pages load), and stubs the Claude artifact API that Ask WarEra expects.
"""
import http.server, os, re, shutil, subprocess, sys, tempfile, threading

SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site")
PAGES = {"index.html": "Updated ", "company.html": "Updated ", "transfers.html": "Updated ", "efficiency.html": "Updated ", "ask.html": "Data updated "}
PROBE = """<script>window.__errs=[];window.addEventListener("error",function(e){__errs.push(String(e.message))});
window.addEventListener("unhandledrejection",function(e){__errs.push("promise: "+String(e.reason&&e.reason.message||e.reason))});
try{localStorage.setItem("we-dev","1")}catch(e){}
window.claude={use:async function(){return{sample:async function(){return{}},save:async function(){}}}};
setTimeout(function(){document.body.setAttribute("data-smoke",JSON.stringify(__errs))},4500)</script>"""


def main(chrome):
    tmp = tempfile.mkdtemp()
    for f in os.listdir(SITE):
        shutil.copy(os.path.join(SITE, f), tmp)
    for p in PAGES:
        path = os.path.join(tmp, p)
        html = open(path, encoding="utf-8").read()
        open(path, "w", encoding="utf-8").write(html.replace("<head>", "<head>" + PROBE, 1))
    handler = lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=tmp)
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    bad = []
    for page, expect in PAGES.items():
        url = f"http://127.0.0.1:{srv.server_address[1]}/{page}"
        dom = subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=8000", "--dump-dom", url],
                             capture_output=True, text=True, timeout=120).stdout
        meta = re.search(r'id="meta"[^>]*>([^<]*)', dom)
        errs = re.search(r'data-smoke="([^"]*)"', dom)
        errs = errs.group(1).replace("&quot;", '"') if errs else "probe did not run"
        ok = bool(meta and meta.group(1).startswith(expect)) and errs == "[]"
        print(f"{'ok  ' if ok else 'FAIL'} {page}: {meta.group(1) if meta else 'no #meta'} | errors: {errs}")
        if not ok:
            bad.append(page)
    srv.shutdown()
    shutil.rmtree(tmp)
    if bad:
        raise SystemExit("pages failed: " + ", ".join(bad))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else shutil.which("google-chrome") or shutil.which("chromium") or "google-chrome")
