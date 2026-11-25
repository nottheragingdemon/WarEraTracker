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
CREATE TABLE IF NOT EXISTS region_rate(region TEXT, t INTEGER, emp REAL, mgr REAL, PRIMARY KEY(region,t));
CREATE TABLE IF NOT EXISTS companies(id TEXT PRIMARY KEY, name TEXT, owner TEXT, item TEXT, value REAL, region TEXT, owner_country TEXT, seen TEXT);
CREATE TABLE IF NOT EXISTS alliances(id TEXT PRIMARY KEY, name TEXT, leader TEXT);
CREATE TABLE IF NOT EXISTS alliance_members(alliance TEXT, country TEXT, PRIMARY KEY(alliance,country));
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, country TEXT, mu TEXT, name TEXT);
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
    db.executescript(SCHEMA)
    return db
