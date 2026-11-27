#!/usr/bin/env python3
"""Diagnose why tracked workers exceed the game's region employee counts (read-only; prints no keys or names).

    WARTRACK_DB=wartrack.sqlite python3 scripts/diag_employees.py "New England" Virginia "Northern Ireland"

For each region: the game's company/employee counts, then for its staffed companies the fields the employee list returns,
how often each field is set, whether the owner is in their own list, and how many listed workers look inactive."""
import collections, datetime as dt, json, os, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wartrack.api import Client  # noqa: E402


def main(names):
    db = sqlite3.connect(os.environ.get("WARTRACK_DB", "wartrack.sqlite")); db.row_factory = sqlite3.Row
    c = Client()
    now = dt.datetime.now(dt.timezone.utc)
    for name in names:
        reg = db.execute("SELECT * FROM region_now WHERE name=?", (name,)).fetchone()
        if not reg:
            print(f"== {name}: not found"); continue
        comps = db.execute("SELECT id, owner, workers FROM companies WHERE region=? AND workers>0 ORDER BY workers DESC LIMIT 60", (reg["region"],)).fetchall()
        print(f"== {name}: game companies {reg['companies']}, game employees {reg['employees']}; tracked staffed (sample) {len(comps)}")
        res = []
        for k in range(0, len(comps), 40):
            res += c.batch([("employee.getCompanyEmployees", {"companyId": r["id"]}) for r in comps[k:k + 40]], official=True)
        host = reg["country"]
        rate = (db.execute("SELECT income FROM country_tax WHERE country=?", (host,)).fetchone() or [0])[0] or 0
        nat = collections.Counter(); natw = collections.Counter(); left = 0; traits = collections.Counter(); wsum = 0.0
        keys, setcount, owner_in, total, ages, vals = collections.Counter(), collections.Counter(), 0, 0, [], collections.defaultdict(collections.Counter)
        for r, lst in zip(comps, res):
            lst = lst if isinstance(lst, list) else []
            for e in lst:
                total += 1
                for k, v in e.items():
                    keys[k] += 1
                    if v not in (None, False, 0, "", [], {}):
                        setcount[k] += 1
                    if isinstance(v, bool) or (isinstance(v, str) and len(v) < 20 and not v[:4].isdigit() and len(v) != 24):
                        vals[k][v] += 1
                    if isinstance(v, str) and v[:4].isdigit() and "T" in v:
                        try:
                            ages.append((k, (now - dt.datetime.fromisoformat(v.replace("Z", "+00:00"))).total_seconds() / 3600))
                        except ValueError:
                            pass
                n = "host" if e.get("nationality") == host else "other"
                nat[n] += 1; natw[n] += float(e.get("wage") or 0); wsum += float(e.get("wage") or 0)
                left += 1 if e.get("leftAt") else 0
                for t in e.get("traits") or []:
                    if isinstance(t, dict) and t.get("code") in ("expat",):
                        traits[(n, t["code"])] += 1
                u = e.get("user") or e.get("userId")
                if isinstance(u, dict):
                    u = u.get("_id")
                if u and u == r["owner"]:
                    owner_in += 1
        print(f"   listed workers {total}; owner in own list {owner_in}")
        print(f"   nationality = host: {nat['host']} workers, wages {natw['host']:.3f}/h; other: {nat['other']} workers, wages {natw['other']:.3f}/h; left: {left}; expat trait: {dict(traits)}")
        allw = db.execute("SELECT COUNT(*), COALESCE(SUM(workers),0), COALESCE(SUM(wages),0) FROM companies WHERE region=?", (reg["region"],)).fetchone()
        print(f"   region: game tax/h {reg['emp']:.3f}; tracked all companies {allw[0]}, workers {allw[1]}, wages {allw[2]:.3f} -> tax {allw[2] * rate / 100:.3f}; sample wage sum {wsum:.3f}")
        print("   fields (present / non-empty):", {k: f"{keys[k]}/{setcount[k]}" for k in keys})
        print("   small values:", {k: dict(v.most_common(6)) for k, v in vals.items()})
        by = collections.defaultdict(list)
        for k, h in ages:
            by[k].append(h)
        for k, hs in by.items():
            hs.sort()
            q = lambda p: round(hs[min(len(hs) - 1, int(p * len(hs)))], 1)
            print(f"   {k} age hours: median {q(.5)}, p75 {q(.75)}, p90 {q(.9)}, >24h {sum(h > 24 for h in hs)}, >72h {sum(h > 72 for h in hs)}")
        if res and isinstance(res[0], list) and res[0]:
            sample = {k: (type(v).__name__ if k in ("user", "userId", "_id", "company") else v) for k, v in res[0][0].items()}
            print("   one entry (ids hidden):", json.dumps(sample, default=str)[:600])


if __name__ == "__main__":
    main(sys.argv[1:] or ["New England", "Virginia", "Northern Ireland"])
