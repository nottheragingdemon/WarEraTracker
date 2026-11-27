"""Keeping the history database small."""
import os
import datetime as dt

from .common import log


def prune(db, days=None):
    """Keep the database small: drop data older than `days` (default 90, $WARTRACK_KEEP_DAYS) and thin bounty snapshots older
    than a week to the last one per day. The exported site only ever shows data inside the window."""
    days = float(days or os.environ.get("WARTRACK_KEEP_DAYS", "90"))
    now = dt.datetime.now(dt.timezone.utc)
    iso = lambda d: (now - dt.timedelta(days=d)).isoformat(timespec="seconds").replace("+00:00", "Z")
    ms = lambda d: int((now - dt.timedelta(days=d)).timestamp() * 1000)
    cut, cut_ms = iso(days), ms(days)
    before = db.total_changes
    old = [r["id"] for r in db.execute("SELECT id FROM battles WHERE created_at<? AND is_active=0", (cut,))]
    for i in range(0, len(old), 500):
        ch = old[i:i + 500]; ph = ",".join("?" * len(ch))
        for t, col in (("battle_stat", "battle_id"), ("battle_fetch", "battle_id"), ("orders", "battle_id"), ("contracts", "battle_id"), ("battles", "id")):
            db.execute(f"DELETE FROM {t} WHERE {col} IN ({ph})", ch)
    db.execute("DELETE FROM bounty_snap WHERE ts<?", (cut,))
    # older than a week: keep only the last snapshot of each day per ranking entry
    db.execute("""DELETE FROM bounty_snap WHERE ts<? AND ts NOT IN (
        SELECT MAX(ts) FROM bounty_snap WHERE ts<? GROUP BY substr(ts,1,10))""", (iso(7), iso(7)))
    for t, col in (("transfers", "ts"), ("donations", "ts")):
        db.execute(f"DELETE FROM {t} WHERE {col}<?", (cut,))
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("region_rate", "wage_snap", "wage_snap2", "wage_snap3", "wage_snap_reg", "full_hist", "run_log", "country_income"):
        if t in tables:
            db.execute(f"DELETE FROM {t} WHERE t<?", (cut_ms,))
    for t in ("wage_snap", "wage_snap2"):   # retired formats: drop once nothing in them is inside the 92-day company history
        if t in tables and not db.execute(f"SELECT 1 FROM {t} WHERE t>=? LIMIT 1", (ms(92),)).fetchone():
            db.execute(f"DROP TABLE {t}"); log(f"prune: retired table {t} dropped")
    db.execute("DELETE FROM company_skip WHERE checked<?", (iso(7),))
    db.execute("DELETE FROM player_snap WHERE day<?", (cut[:10],))
    db.execute("DELETE FROM coverage_hist WHERE day<?", (cut[:10],))
    db.execute("DELETE FROM player_skill_hist WHERE checked<?", (cut,))
    db.execute("DELETE FROM run_stats WHERE ts<?", (iso(14),))
    db.commit()
    log(f"prune: {db.total_changes - before} old rows removed (keeping {days:g} days)")
    compact(db, now)


def db_bytes(db):
    return db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0]


def compact(db, now=None, every_days=7):
    """Once a week, rebuild the file to give back the space of deleted rows (VACUUM), and record the size once a day for the
    Status page's trend."""
    now = now or dt.datetime.now(dt.timezone.utc)
    meta = lambda k: (db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone() or [None])[0]
    last = meta("vacuum_at")
    if not last or (now - dt.datetime.fromisoformat(last)).total_seconds() >= every_days * 86400:
        size0 = db_bytes(db)
        db.commit()
        db.execute("VACUUM")
        db.execute("INSERT OR REPLACE INTO meta VALUES('vacuum_at',?)", (now.isoformat(timespec="seconds"),))
        db.commit()
        log(f"compact: {size0 / 1e6:.1f} MB -> {db_bytes(db) / 1e6:.1f} MB")
    db.execute("INSERT OR REPLACE INTO db_size VALUES(?,?)", (now.date().isoformat(), db_bytes(db)))
    db.execute("DELETE FROM db_size WHERE day<?", ((now - dt.timedelta(days=90)).date().isoformat(),))
    db.commit()
