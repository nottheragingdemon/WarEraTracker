#!/usr/bin/env python3
"""Fail if a tracked file looks like it holds a secret (a GitHub token, a Discord webhook URL, a long key assigned in code, a link with ?key=<value>).

    python3 scripts/secret_scan.py            # every file git tracks in this repository
"""
import os, re, subprocess, sys

PATTERNS = [
    ("a GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("a Discord webhook URL", re.compile(r"discord(?:app)?\.com/api/webhooks/\d{6,}/[\w-]{20,}")),
    ("a key assigned in code", re.compile(r"""(?i)\b(?:api[_-]?key|token|secret|password)\b["']?\s*[:=]\s*["'][A-Za-z0-9_\-]{24,}["']""")),
    ("a link with a key in it", re.compile(r"[?&]key=[A-Za-z0-9_\-]{12,}")),
]
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".xz", ".sqlite", ".woff", ".woff2")


def scan_text(text):
    """[(what, excerpt)] for the secrets in one text."""
    out = []
    for what, pat in PATTERNS:
        for m in pat.finditer(text):
            val = m.group(0)
            if "${{" in text[max(0, m.start() - 4):m.end() + 4] or re.search(r"(?i)example|placeholder|your[_-]|xxxx", val):
                continue
            out.append((what, val[:12] + "…"))
    return out


def tracked_files(root):
    r = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
    return [f for f in r.stdout.splitlines() if not f.lower().endswith(SKIP_EXT)]


def scan_repo(root):
    found = []
    for f in tracked_files(root):
        try:
            text = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        # base64 screenshots etc. are long runs without spaces: only look at text outside data: URIs
        text = re.sub(r"data:[a-z/+-]+;base64,[A-Za-z0-9+/=]+", "", text)
        found += [(f, what, ex) for what, ex in scan_text(text)]
    return found


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bad = scan_repo(root)
    for f, what, ex in bad:
        print(f"PROBLEM: {f} looks like it holds {what} ({ex})")
    print("secret scan:", "FAILED" if bad else "clean")
    sys.exit(1 if bad else 0)
