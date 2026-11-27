"""Shared helpers for the collector stages: time parsing, logging, the alliance scope."""
import os
import json, datetime as dt, re


ISO = "%Y-%m-%dT%H:%M:%S.%fZ"


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime(ISO)[:-4] + "Z"


def parse_when(s, default=None):
    """'7d', '36h', '2026-11-20' or full ISO -> ISO string (UTC)."""
    if not s:
        return default
    m = re.fullmatch(r"(\d+)([dhm])", s.strip())
    if m:
        n, u = int(m.group(1)), m.group(2)
        delta = {"d": dt.timedelta(days=n), "h": dt.timedelta(hours=n), "m": dt.timedelta(minutes=n)}[u]
        return (dt.datetime.now(dt.timezone.utc) - delta).strftime(ISO)[:-4] + "Z"
    if len(s) == 10:
        s += "T00:00:00.000Z"
    return s


def log(*a):
    print(*a, flush=True)


class Scope:
    """What to collect: battles involving a member country of one alliance, created since a date."""
    def __init__(self, db, alliance=None, since=None):
        self.alliance_id, self.members, self.since = None, set(), since
        if alliance:
            r = db.execute("SELECT eid FROM names WHERE etype='alliance' AND (eid=? OR lower(name)=lower(?))", (alliance, alliance)).fetchone()
            if not r:
                raise SystemExit(f"alliance '{alliance}' not found; run `collect --what alliances` first (needs an API key)")
            self.alliance_id = r["eid"]
            self.members = {m["country"] for m in db.execute("SELECT country FROM alliance_members WHERE alliance=?", (self.alliance_id,))}

    @property
    def active(self):
        return bool(self.alliance_id)

    def battle_sql(self, alias="b"):
        """SQL condition (with args) restricting a battles table to the scope."""
        conds, args = [], []
        if self.since:
            conds.append(f"{alias}.created_at>=?"); args.append(self.since)
        if self.members:
            ph = ",".join("?" * len(self.members))
            conds.append(f"({alias}.att_country IN ({ph}) OR {alias}.def_country IN ({ph}))")
            args += list(self.members) * 2
        return (" AND ".join(conds) or "1=1"), args


def alliance_countries(db):
    """member countries of the alliance named in scope.json (empty if none)"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scope.json")
    name = json.load(open(path)).get("alliance") if os.path.exists(path) else None
    if not name:
        return set()
    return {r[0] for r in db.execute("SELECT am.country FROM alliance_members am JOIN alliances a ON a.id=am.alliance WHERE a.name=?", (name,))}
