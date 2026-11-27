import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS battles(
  id TEXT PRIMARY KEY, war TEXT, type TEXT, created_at TEXT, ended_at TEXT, is_active INT,
  att_country TEXT, def_country TEXT, def_region TEXT, won_by TEXT,
  att_damage INT, def_damage INT, att_hits INT, def_hits INT, rounds_json TEXT, details_at TEXT);
CREATE TABLE IF NOT EXISTS battle_stat(
  battle_id TEXT, kind TEXT, etype TEXT, eid TEXT, side TEXT, value REAL, PRIMARY KEY(battle_id,kind,etype,eid,side));
CREATE INDEX IF NOT EXISTS bst_e ON battle_stat(etype,eid);
CREATE TABLE IF NOT EXISTS battle_fetch(battle_id TEXT, level TEXT, fetched_at TEXT, PRIMARY KEY(battle_id,level));
CREATE TABLE IF NOT EXISTS mus(id TEXT PRIMARY KEY, name TEXT, country TEXT);
CREATE TABLE IF NOT EXISTS mu_members(mu TEXT, user TEXT, PRIMARY KEY(mu,user));
CREATE INDEX IF NOT EXISTS mm_u ON mu_members(user);
CREATE VIEW IF NOT EXISTS battle_damage AS
  SELECT battle_id, etype, eid, SUM(value) AS value FROM battle_stat WHERE kind='damage' GROUP BY battle_id, etype, eid;
CREATE TABLE IF NOT EXISTS orders(
  battle_id TEXT, side TEXT, kind TEXT, eid TEXT, first_seen TEXT, last_seen TEXT,
  PRIMARY KEY(battle_id,side,kind,eid));
CREATE TABLE IF NOT EXISTS bounty_snap(
  ts TEXT, rtype TEXT, eid TEXT, value REAL, country TEXT, mu TEXT, PRIMARY KEY(ts,rtype,eid));
CREATE INDEX IF NOT EXISTS bs_e ON bounty_snap(rtype,eid,ts);
CREATE TABLE IF NOT EXISTS contracts(
  id TEXT PRIMARY KEY, battle_id TEXT, country TEXT, created_by TEXT, for_country TEXT, side TEXT,
  min_damage REAL, budget REAL, initial_perk REAL, current_perk REAL, current_payout REAL, duration INT,
  status TEXT, created_at TEXT, expires_at TEXT, winner_mu TEXT, winner_user TEXT, bids_json TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS names(etype TEXT, eid TEXT, name TEXT, country TEXT, PRIMARY KEY(etype,eid));
CREATE TABLE IF NOT EXISTS run_log(t INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS coverage_hist(day TEXT, host TEXT, staffed INTEGER, game_companies INTEGER, workers INTEGER, game_workers INTEGER, tax REAL, game_tax REAL, PRIMARY KEY(day, host));
CREATE TABLE IF NOT EXISTS company_loc(id TEXT PRIMARY KEY, region TEXT, owner TEXT, disabled INTEGER, checked TEXT, listed INTEGER);
CREATE TABLE IF NOT EXISTS wage_snap_reg(region TEXT, owner_country TEXT, t INTEGER, companies INTEGER, workers INTEGER, wages REAL, mgr REAL, PRIMARY KEY(region, owner_country, t));
CREATE TABLE IF NOT EXISTS wage_snap3(host TEXT, core TEXT, owner_country TEXT, t INTEGER, companies INTEGER, workers INTEGER, wages REAL, mgr REAL, PRIMARY KEY(host, core, owner_country, t));
CREATE TABLE IF NOT EXISTS trades(id TEXT, ts TEXT, country TEXT, buyer_country TEXT, money REAL, item TEXT, quantity REAL, PRIMARY KEY(id, country));
CREATE TABLE IF NOT EXISTS country_income(country TEXT, t INTEGER, money REAL, income TEXT, PRIMARY KEY(country, t));
CREATE TABLE IF NOT EXISTS run_stats(ts TEXT PRIMARY KEY, kind TEXT, seconds REAL, calls INTEGER, gw INTEGER, skipped TEXT, timings TEXT);
CREATE TABLE IF NOT EXISTS player_snap(eid TEXT, day TEXT, wealth REAL, dmg_total REAL, dmg_week REAL, ts TEXT, PRIMARY KEY(eid, day));
CREATE TABLE IF NOT EXISTS player_skill(eid TEXT PRIMARY KEY, checked TEXT, reset_at TEXT, spent INTEGER, eco INTEGER, levels TEXT);
CREATE TABLE IF NOT EXISTS player_skill_hist(eid TEXT, checked TEXT, spent INTEGER, eco INTEGER, PRIMARY KEY(eid, checked));
CREATE TABLE IF NOT EXISTS player_now(eid TEXT PRIMARY KEY, country TEXT, mu TEXT, name TEXT, wealth REAL, dmg_total REAL, dmg_week REAL, ts TEXT);
CREATE TABLE IF NOT EXISTS region_rate(region TEXT, t INTEGER, emp REAL, mgr REAL, PRIMARY KEY(region,t));
CREATE TABLE IF NOT EXISTS companies(id TEXT PRIMARY KEY, name TEXT, owner TEXT, item TEXT, value REAL, region TEXT, owner_country TEXT, seen TEXT, workers INT, wages REAL, mgr REAL);
CREATE TABLE IF NOT EXISTS region_now(region TEXT PRIMARY KEY, name TEXT, country TEXT, emp REAL, mgr REAL, res REAL, companies INT, employees INT, core TEXT);
CREATE TABLE IF NOT EXISTS country_tax(country TEXT PRIMARY KEY, name TEXT, income REAL, manager REAL, market REAL);
CREATE TABLE IF NOT EXISTS country_now(country TEXT PRIMARY KEY, name TEXT, money REAL, wealth REAL, wealth_rank INT, population INT, development REAL, updated TEXT);
CREATE TABLE IF NOT EXISTS wealth_now(eid TEXT PRIMARY KEY, country TEXT, mu TEXT, value REAL, rank INT, updated TEXT);
CREATE TABLE IF NOT EXISTS transfers(id TEXT PRIMARY KEY, ts TEXT, sender TEXT, receiver TEXT, money REAL);
CREATE INDEX IF NOT EXISTS transfers_ts ON transfers(ts);
CREATE TABLE IF NOT EXISTS donations(id TEXT PRIMARY KEY, ts TEXT, country TEXT, donor TEXT, money REAL, donor_country TEXT);
CREATE INDEX IF NOT EXISTS donations_ts ON donations(ts);
CREATE TABLE IF NOT EXISTS company_skip(id TEXT PRIMARY KEY, checked TEXT);
CREATE TABLE IF NOT EXISTS rate_hist(country TEXT, t INTEGER, income REAL, manager REAL, PRIMARY KEY(country,t));
CREATE TABLE IF NOT EXISTS alliances(id TEXT PRIMARY KEY, name TEXT, leader TEXT);
CREATE TABLE IF NOT EXISTS alliance_members(alliance TEXT, country TEXT, PRIMARY KEY(alliance,country));
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, country TEXT, mu TEXT, name TEXT);
"""


# wage history formats used before 27 Nov 2026; no longer written. Kept only while they hold rows (the prune drops them
# once their last row ages out); created here for tests of the old-history export.
LEGACY_WAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS wage_snap(region TEXT, owner_country TEXT, t INTEGER, companies INT, workers INT, wages REAL, mgr REAL, PRIMARY KEY(region,owner_country,t));
CREATE TABLE IF NOT EXISTS wage_snap2(host TEXT, owner_country TEXT, t INTEGER, companies INTEGER, workers INTEGER, wages REAL, mgr REAL, PRIMARY KEY(host, owner_country, t));
"""


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    # migrate from the first schema: battle_damage was a table, now a view over battle_stat
    t = db.execute("SELECT type FROM sqlite_master WHERE name='battle_damage'").fetchone()
    if t and t[0] == "table":
        db.execute("DROP TABLE battle_damage")
    cols = [r[1] for r in db.execute("PRAGMA table_info(users)")]
    if cols and "name" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN name TEXT")
    ccols = [r[1] for r in db.execute("PRAGMA table_info(companies)")]
    for col, typ in (("workers", "INT"), ("wages", "REAL"), ("mgr", "REAL")):
        if ccols and col not in ccols:
            db.execute(f"ALTER TABLE companies ADD COLUMN {col} {typ}")
    wcols = [r[1] for r in db.execute("PRAGMA table_info(wage_snap)")]
    if wcols and "mgr" not in wcols:
        db.execute("ALTER TABLE wage_snap ADD COLUMN mgr REAL")
    lcols = [r[1] for r in db.execute("PRAGMA table_info(company_loc)")]
    if lcols and "listed" not in lcols:
        db.execute("ALTER TABLE company_loc ADD COLUMN listed INTEGER")   # the full-list pass the company was last seen in
    tcols = [r[1] for r in db.execute("PRAGMA table_info(trades)")]
    if tcols and "buyer_country" not in tcols:   # first version attributed trades to the buyer's country: rebuild and backfill again
        db.execute("DROP TABLE trades")
        db.execute("DELETE FROM meta WHERE k LIKE 'trades_back_%'") if [1 for r in db.execute("SELECT name FROM sqlite_master WHERE name='meta'")] else None
    db.executescript(SCHEMA)
    if "income" not in [r[1] for r in db.execute("PRAGMA table_info(country_now)")]:
        db.execute("ALTER TABLE country_now ADD COLUMN income TEXT")   # the game's hourly income per stream, as JSON
    if "core" not in [r[1] for r in db.execute("PRAGMA table_info(region_now)")]:
        db.execute("ALTER TABLE region_now ADD COLUMN core TEXT")   # the region's original country (it gets a share of tax when conquered)
    return db
