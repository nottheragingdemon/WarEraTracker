#!/usr/bin/env python3
"""Refresh the phone screenshots in site/guide.html from the current pages (headless Chrome, 420 px wide).

    python3 scripts/guide_shots.py [chrome binary]

Each screenshot is an <img> whose alt text starts with the page it shows (SHOTS below); the picture and the date in its caption are replaced.
"""
import base64, datetime as dt, functools, http.server, io, os, re, shutil, subprocess, sys, tempfile, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
SHOTS = {"company": "The company tax tracker on a phone", "status": "The Status page on a phone"}



def shoot(chrome, port, page, out):
    subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--window-size=420,1500",
                    "--virtual-time-budget=9000", f"--screenshot={out}", f"http://localhost:{port}/{page}.html"],
                   check=True, capture_output=True, timeout=120)


def jpeg(path):
    from PIL import Image
    b = io.BytesIO()
    Image.open(path).convert("RGB").crop((0, 0, 420, 1500)).save(b, "JPEG", quality=72, optimize=True)
    return base64.b64encode(b.getvalue()).decode()


def main(chrome):
    tmp = tempfile.mkdtemp()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SITE)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    guide = open(os.path.join(SITE, "guide.html"), encoding="utf-8").read()
    today = dt.date.today().strftime("%-d %b %Y")
    for page, alt in SHOTS.items():
        png = os.path.join(tmp, page + ".png")
        shoot(chrome, srv.server_address[1], page, png)
        data = jpeg(png)
        pat = re.compile(r'(<summary>What it looks like \(example from )[^)]*(\)</summary><img src=")data:image/jpeg;base64,[A-Za-z0-9+/=]+(" alt="' + re.escape(alt) + ')')
        guide, n = pat.subn(lambda m: m.group(1) + today + m.group(2) + "data:image/jpeg;base64," + data + m.group(3), guide)
        print(f"{page}: {'updated' if n else 'NOT FOUND in the guide'}")
        if not n:
            return 1
    open(os.path.join(SITE, "guide.html"), "w", encoding="utf-8").write(guide)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else shutil.which("google-chrome") or "/usr/bin/google-chrome"))
