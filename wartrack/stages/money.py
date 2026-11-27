"""Money moving between and into the alliance's countries: transfers, citizen donations, market trades."""
import datetime as dt

from .common import log, now_iso


def collect_transfers(c, db, scope=None, days=90):
    """Country money transfers between the alliance's member countries (transactionType countryMoneyTransfer).
    Newest first per country; stops at the first transaction already stored or older than `days`."""
    members = set(scope.members) if scope and scope.members else set()
    if not members:
        log("transfers: no alliance members in scope, skipped"); return
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    known = {r["id"] for r in db.execute("SELECT id FROM transfers")}
    new = 0
    def fresh(m):   # newest first until something already stored or too old
        out = []
        for t in c.pages("transaction.getPaginatedTransactions", max_pages=60, countryId=m, transactionType="countryMoneyTransfer", limit=100):
            if t["_id"] in known or t["createdAt"] < cutoff:
                break
            out.append(t)
        return out
    for found in c.map(fresh, sorted(members)):   # the countries are read in parallel, written one after another
        for t in found:
            if t.get("sellerCountryId") in members and t.get("buyerCountryId") in members:
                db.execute("INSERT OR IGNORE INTO transfers VALUES(?,?,?,?,?)", (t["_id"], t["createdAt"], t["sellerCountryId"], t["buyerCountryId"], t.get("money") or 0))
                new += 1
    db.commit()
    log(f"transfers: {new} new between member countries")


def collect_trades(c, db, scope=None, days=30, budget=120.0):
    """Market trades (transactionType trading) the game lists under each member country, newest first; stops at the first
    one already stored or older than `days`, with a one-off backfill. The game lists a trade under more than the buyer's
    country (most likely the seller's too), so each trade is kept per member country it was listed under. Used to estimate market tax."""
    import time as _t
    members = sorted(scope.members) if scope and scope.members else []
    if not members:
        log("trades: no alliance members in scope, skipped"); return
    t0 = _t.monotonic()
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    known = {(r["id"], r["country"]) for r in db.execute("SELECT id, country FROM trades")}
    done_key = f"trades_back_{days:g}"
    backfill = {m for m in members if not db.execute("SELECT 1 FROM meta WHERE k=?", (f"{done_key}_{m}",)).fetchone()}
    reached = set()

    def fresh(m):
        out, back = [], m in backfill
        for t in c.pages("transaction.getPaginatedTransactions", max_pages=60 if back else 20, countryId=m, transactionType="trading", limit=100):
            if t["createdAt"] < cutoff:
                reached.add(m); break
            if _t.monotonic() - t0 > budget:
                break
            if (t["_id"], m) in known:
                if back:
                    continue
                break
            out.append(t)
        else:
            reached.add(m)
        return out
    new = 0
    for m, found in zip(members, c.map(fresh, members)):
        for t in found:
            db.execute("INSERT OR IGNORE INTO trades VALUES(?,?,?,?,?,?,?)",
                       (t["_id"], t["createdAt"], m, t.get("buyerCountryId"), t.get("money") or 0, t.get("itemCode"), t.get("quantity")))
            new += 1
    for m in backfill & reached:
        db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (f"{done_key}_{m}", now_iso()))
    db.execute("DELETE FROM trades WHERE ts < ?", (cutoff,))
    db.commit()
    log(f"trades: {new} new market trades" + (f", backfilled {len(backfill & reached)} of {len(backfill)} countries" if backfill else ""))


def collect_donations(c, db, scope=None, days=90, budget=300.0):
    """Player donations to each member country's treasury (transactionType donation), newest first; stops at the first
    one already stored or older than `days`. The donor's own country is looked up so citizens' donations can be separated."""
    import time as _t
    members = set(scope.members) if scope and scope.members else set()
    if not members:
        log("donations: no alliance members in scope, skipped"); return
    t0 = _t.monotonic()
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    known = {r["id"] for r in db.execute("SELECT id FROM donations")}
    new = 0
    # a country whose stored donations don't yet reach back `days` is read past the ones already stored (a one-off backfill)
    done_key = f"donations_back_{days:g}"
    backfill = {m for m in members if not db.execute("SELECT 1 FROM meta WHERE k=?", (f"{done_key}_{m}",)).fetchone()}
    reached = set()

    def fresh(m):
        out, back = [], m in backfill
        for t in c.pages("transaction.getPaginatedTransactions", max_pages=200 if back else 80, countryId=m, transactionType="donation", limit=100):
            if t["createdAt"] < cutoff:
                reached.add(m); break
            if _t.monotonic() - t0 > budget:
                break
            if t["_id"] in known:
                if back:
                    continue
                break
            out.append(t)
        else:
            reached.add(m)   # the list ended: nothing older exists
        return out
    for m, found in zip(sorted(members), c.map(fresh, sorted(members))):
        for t in found:
            if t.get("sellerCountryId") == m and t.get("buyerId"):
                row = db.execute("SELECT country FROM users WHERE id=?", (t["buyerId"],)).fetchone()
                db.execute("INSERT OR IGNORE INTO donations VALUES(?,?,?,?,?,?)", (t["_id"], t["createdAt"], m, t["buyerId"], t.get("money") or 0, row["country"] if row else None))
                new += 1
    db.commit()
    need = [r["donor"] for r in db.execute("SELECT DISTINCT donor FROM donations WHERE donor_country IS NULL")]
    looked = 0
    for u, d in c.lookup_users(need).items():
        if d.get("country"):
            db.execute("UPDATE donations SET donor_country=? WHERE donor=?", (d["country"], u)); looked += 1
    for m in backfill & reached:
        db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (f"{done_key}_{m}", now_iso()))
    if backfill:
        log(f"donations: backfilled {len(backfill & reached)} of {len(backfill)} countries to {days:g} days")
    db.execute("DELETE FROM donations WHERE ts < ?", (cutoff,))
    db.commit()
    nameless = [r["donor"] for r in db.execute("SELECT DISTINCT d.donor FROM donations d LEFT JOIN users u ON u.id=d.donor WHERE d.donor_country=d.country AND (u.name IS NULL)")]
    for u, d in c.lookup_users(nameless).items():
        if d.get("username"):
            db.execute("INSERT INTO users(id,name,country) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name", (u, d["username"], d.get("country")))
            db.execute("INSERT OR REPLACE INTO names VALUES('user',?,?,NULL)", (u, d["username"]))
    db.commit()
    log(f"donations: {new} new, {looked} donors looked up, {len(need) - looked} still unknown")
