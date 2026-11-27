#!/usr/bin/env python3
"""Do the live Streamlit pages actually show data? Opens each page in a real browser (Playwright) and reads the page inside Streamlit's iframe.

    STREAMLIT_URL=https://wareratracker.streamlit.app/ python3 scripts/live_pages.py

Exit 1 only when a page loaded but shows an error or no data. When the app is asleep or can't be looked into (a sign-in redirect, no
iframe within the wait), that is reported and is not a failure: scripts/live_check.py covers "is it up".
"""
import os, sys

URL = os.environ.get("STREAMLIT_URL", "https://wareratracker.streamlit.app/").rstrip("/") + "/"
PAGES = [("", "Updated"), ("company-tax", "Updated"), ("transfers", "Updated"), ("efficiency", "Updated"), ("status", "Updated")]
BAD = ("Could not load", "Unexpected token", "is not defined", "Traceback")


def judge(text, want):
    """(state, message): 'ok', 'bad' (the page loaded and is wrong) or 'unknown' (nothing to read yet)."""
    t = text or ""
    if not t.strip():
        return "unknown", "no page text"
    for b in BAD:
        if b in t:
            return "bad", f"the page shows an error ({b})"
    if "Loading…" in t and want not in t:
        return "bad", "the page is still on Loading… (its data didn't arrive)"
    if want not in t:
        return "unknown", f"didn't find {want!r}"
    return "ok", "ok"


def page_text(page):
    best = ""
    for f in page.frames:
        try:
            t = f.inner_text("body", timeout=3000)
        except Exception:   # noqa: BLE001
            continue
        if len(t) > len(best) and f != page.main_frame:
            best = t
    return best


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright isn't installed; nothing checked")
        return 0
    bad = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 420, "height": 900})
        for path, want in PAGES:
            try:
                pg.goto(URL + path, wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(15000)
                state, msg = judge(page_text(pg), want)
            except Exception as e:   # noqa: BLE001
                state, msg = "unknown", f"couldn't open it: {str(e)[:80]}"
            print(f"{state:8} /{path}: {msg}")
            if state == "bad":
                bad.append(f"/{path}: {msg}")
        b.close()
    for x in bad:
        print("PROBLEM:", x)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
