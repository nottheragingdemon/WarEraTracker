#!/usr/bin/env python3
"""Is the live Streamlit app up? Exit 1 (with a message) when it isn't.

    STREAMLIT_URL=https://wareratracker.streamlit.app/ python3 scripts/live_check.py

Checks the app's health endpoint and that the page answers. An app that has gone to sleep (free apps do after a while without
visitors) is reported as asleep, not as a failure. What is *inside* the app is covered by the tests (scripts/smoke_pages.py --streamlit):
the pages run in an iframe, which a plain request can't read.
"""
import os, sys, urllib.error, urllib.request

URL = os.environ.get("STREAMLIT_URL", "https://wareratracker.streamlit.app/").rstrip("/") + "/"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "warera-live-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read(200000).decode("utf-8", "replace")


def check(fetch=get, url=URL):
    """(ok, message)."""
    try:
        status, body = fetch(url)
    except urllib.error.HTTPError as e:
        return False, f"{url} answered HTTP {e.code}"
    except Exception as e:   # noqa: BLE001
        return False, f"{url} could not be reached: {e}"
    if "get this app back up" in body.lower():
        return True, "the app is asleep (it wakes on the next visit)"
    try:
        hs, hb = fetch(url + "_stcore/health")
    except Exception as e:   # noqa: BLE001
        return False, f"the app's health check failed: {e}"
    if hs != 200 or hb.strip().lower() != "ok":
        return False, f"the app's health check says {hb.strip()[:60]!r} (HTTP {hs})"
    return True, "the app is up"


if __name__ == "__main__":
    ok, msg = check()
    print(("ok: " if ok else "PROBLEM: ") + msg)
    sys.exit(0 if ok else 1)
