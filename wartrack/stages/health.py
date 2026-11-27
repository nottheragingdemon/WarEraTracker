"""Freshness checks: is each kind of data still arriving as often as it should? A stage that silently stops saving data
(no crash, nothing skipped) shows up here as stale. Used by the alerts step (Discord) and the Status page."""
import datetime as dt

# name, what it means, SQL giving the newest time (ISO text, epoch ms or a YYYY-MM-DD day), hours allowed
CHECKS = [
    ("refresh", "Hourly full refresh ran", "SELECT MAX(ts) FROM run_stats WHERE kind='full'", 2.5),
    ("sample", "15-minute battle and tax check ran", "SELECT MAX(ts) FROM run_stats WHERE kind='sample'", 2.0),   # GitHub often runs it only hourly at busy times
    ("index", "Daily company index ran", "SELECT MAX(ts) FROM run_stats WHERE kind='index'", 30),
    ("regions", "Region tax rates checked", "SELECT MAX(t) FROM run_log", 1.5),
    ("countries", "Country treasuries and taxes updated", "SELECT MAX(updated) FROM country_now", 2.0),
    ("income", "Country income history recorded", "SELECT MAX(t) FROM country_income", 2.5),
    ("rankings", "Battle rankings fetched", "SELECT MAX(fetched_at) FROM battle_fetch", 12),
    ("bounty", "Bounty rankings snapshot", "SELECT MAX(ts) FROM bounty_snap", 3),
    ("wealth", "Player wealth ranking updated", "SELECT MAX(updated) FROM wealth_now", 3),
    ("companies", "Companies refreshed", "SELECT MAX(seen) FROM companies", 3),
    ("coverage", "Company coverage recorded", "SELECT MAX(day) FROM coverage_hist", 50),
    ("players", "Player efficiency snapshot", "SELECT MAX(ts) FROM player_snap", 3),
    ("contracts", "Mercenary contracts read in full", "SELECT v FROM meta WHERE k='contracts_full_at'", 6),
    ("donations", "Newest citizen donation", "SELECT MAX(ts) FROM donations", 24),
    ("trades", "Newest market trade", "SELECT MAX(ts) FROM trades", 72),
    ("transfers", "Newest money transfer between alliance nations", "SELECT MAX(ts) FROM transfers", 168),
]


def _when(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        return dt.datetime.fromtimestamp(int(v) / 1000, dt.timezone.utc)
    s = str(v)
    if len(s) == 10:   # a day: counts from its start (so the limit allows for a full day plus a margin)
        return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def freshness(db, now=None):
    """[{key, label, last (ISO or None), age_h, limit_h, state: ok | stale | none}]"""
    now = now or dt.datetime.now(dt.timezone.utc)
    out = []
    for key, label, sql, limit in CHECKS:
        try:
            last = _when(db.execute(sql).fetchone()[0])
        except Exception:   # table not created yet
            last = None
        age = (now - last).total_seconds() / 3600 if last else None
        out.append({"key": key, "label": label, "last": last.isoformat(timespec="seconds") if last else None,
                    "age_h": round(age, 2) if age is not None else None, "limit_h": limit,
                    "state": "none" if last is None else ("ok" if age <= limit else "stale")})
    return out
