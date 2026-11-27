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


SCOPE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scope.json")   # repo root


AGREEMENTS_FILE = os.path.join(os.path.dirname(SCOPE_FILE), "agreements.json")   # repo root; edited from the Streamlit Settings page


def tax_agreements(db, path=None):
    """{host country id: {partner country id: set of covered region ids, or None for all the host's regions}} from
    agreements.json, by name: {"Ireland": [{"country": "Mexico", "regions": "core"}, {"country": "United Kingdom",
    "regions": ["Northern Ireland"]}]}. "regions" is "all" (the default; a bare country name means that too), "core" (the
    host's own original regions, not conquered ones) or a list of region names. None when the file doesn't exist (then every
    alliance country is a host and every owner is tracked)."""
    path = path or AGREEMENTS_FILE
    if not os.path.exists(path):
        return None
    try:
        cfg = json.load(open(path)).get("agreements") or {}
    except (ValueError, OSError):
        return None
    ids = {r[1]: r[0] for r in db.execute("SELECT country, name FROM country_tax")}
    regs = db.execute("SELECT region, name, country, core FROM region_now").fetchall()
    out = {}
    for host, items in cfg.items():
        h = ids.get(host)
        if not h:
            continue
        out[h] = {}
        for it in items or []:
            name, scope = (it, "all") if isinstance(it, str) else (it.get("country"), it.get("regions", "all"))
            if name not in ids:
                continue
            if scope in (None, "all"):
                cover = None
            elif scope == "core":
                cover = {r[0] for r in regs if r[2] == h and (r[3] or r[2]) == h}
            else:
                want = set(scope) if isinstance(scope, list) else {scope}
                cover = {r[0] for r in regs if r[2] == h and r[1] in want}
            out[h][ids[name]] = cover
    return out


def agreement_covers(ag, host, owner_country, region):
    """Whether a company (its host, owner's country and region) falls under a tax agreement; True when there are no agreements."""
    if ag is None:
        return True
    cover = ag.get(host, {})
    if owner_country not in cover:
        return False
    return cover[owner_country] is None or region in cover[owner_country]


def company_hosts(db, scope=None):
    """The host countries whose companies are collected: those with a tax agreement, else the alliance's countries."""
    ag = tax_agreements(db)
    if ag is not None:
        return set(ag)
    return alliance_countries(db) or set(scope.members if scope and scope.members else [])


def alliance_countries(db):
    """member countries of the alliance named in scope.json (empty if none)"""
    path = SCOPE_FILE
    name = json.load(open(path)).get("alliance") if os.path.exists(path) else None
    if not name:
        return set()
    return {r[0] for r in db.execute("SELECT am.country FROM alliance_members am JOIN alliances a ON a.id=am.alliance WHERE a.name=?", (name,))}
