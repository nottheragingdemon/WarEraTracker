import json, re, csv, sys
from collections import defaultdict

HEX = re.compile(r"^[0-9a-f]{24}$")


class Filters:
    def __init__(self, since, until=None, alliance=None, country=None, mu=None, user=None):
        self.since, self.until = since, until
        self.alliance, self.country, self.mu, self.user = alliance, country, mu, user


# ---------- names ----------
def load_countries(c, db):
    if db.execute("SELECT 1 FROM names WHERE etype='country'").fetchone():
        return
    for x in c.call("country.getAllCountries"):
        db.execute("INSERT OR REPLACE INTO names VALUES('country',?,?,?)", (x["_id"], x["name"], x.get("code")))
    db.commit()


def resolve(c, db, etype, value):
    """Name/code/ID -> ID. Raises ValueError if it can't be resolved."""
    if value is None or HEX.match(value.lower()):
        return value
    v = value.lower()
    r = db.execute("SELECT eid FROM names WHERE etype=? AND (lower(name)=? OR lower(country)=?)", (etype, v, v)).fetchone()
    if r:
        return r["eid"]
    res = c.call("search.searchAnything", searchText=value)
    key = {"mu": "muIds", "user": "userIds", "country": "countryIds", "alliance": "allianceIds"}.get(etype)
    ids = (res or {}).get(key) or []
    if ids:
        db.execute("INSERT OR REPLACE INTO names VALUES(?,?,?,NULL)", (etype, ids[0], value))
        db.commit()
        extra = f" (+{len(ids) - 1} other matches, pass an ID to pick)" if len(ids) > 1 else ""
        print(f"resolved {etype} '{value}' -> {ids[0]}{extra}", file=sys.stderr)
        return ids[0]
    raise ValueError(f"could not resolve {etype} '{value}'")


def name_of(c, db, etype, eid, fetch=True):
    r = db.execute("SELECT name FROM names WHERE etype=? AND eid=?", (etype, eid)).fetchone()
    if r:
        return r["name"]
    if not fetch or c is None:
        return eid
    try:
        if etype == "mu":
            n = c.call("mu.getById", muId=eid)["name"]
        elif etype == "user":
            n = c.call("user.getUserLite", userId=eid)["username"]
        else:
            return eid
    except Exception:
        return eid
    db.execute("INSERT OR REPLACE INTO names VALUES(?,?,?,NULL)", (etype, eid, n))
    db.commit()
    return n


# ---------- battle selection ----------
def battle_ids(db, f):
    sql, args = "SELECT id FROM battles WHERE created_at>=?", [f.since]
    if f.until:
        sql += " AND created_at<?"; args.append(f.until)
    ids = {r[0] for r in db.execute(sql, args)}
    if f.alliance:
        s = {r[0] for r in db.execute("SELECT battle_id FROM battle_damage WHERE etype='alliance' AND eid=?", (f.alliance,))}
        mem = [r[0] for r in db.execute("SELECT country FROM alliance_members WHERE alliance=?", (f.alliance,))]
        for i in range(0, len(mem), 400):
            ch = mem[i:i + 400]; ph = ",".join("?" * len(ch))
            s |= {r[0] for r in db.execute(f"SELECT id FROM battles WHERE att_country IN ({ph}) OR def_country IN ({ph})", ch + ch)}
        ids &= s
    for etype, val in (("mu", f.mu), ("user", f.user)):
        if val:
            ids &= {r[0] for r in db.execute("SELECT battle_id FROM battle_damage WHERE etype=? AND eid=?", (etype, val))}
    if f.country:
        s = {r[0] for r in db.execute("SELECT id FROM battles WHERE att_country=? OR def_country=?", (f.country, f.country))}
        s |= {r[0] for r in db.execute("SELECT battle_id FROM battle_damage WHERE etype='country' AND eid=?", (f.country,))}
        s |= {r[0] for r in db.execute("SELECT battle_id FROM orders WHERE kind='country' AND eid=?", (f.country,))}
        ids &= s
    return ids


def q(db, sql, ids, extra=()):
    ids = list(ids)
    out = []
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        out += db.execute(sql.replace("{IN}", ",".join("?" * len(chunk))), (*chunk, *extra)).fetchall()
    return out


# ---------- reports ----------
def damage(db, f, by="auto", top=20):
    ids = battle_ids(db, f)
    if by == "auto":
        by = "user" if f.user else "mu" if f.mu else "country" if f.country else "alliance" if f.alliance else "battle"
    if by == "battle":
        spec = next(((t, v) for t, v in (("user", f.user), ("mu", f.mu), ("alliance", f.alliance), ("country", f.country)) if v), None)
        if spec:
            t, v = spec
            rows = []
            idl = list(ids)
            for i in range(0, len(idl), 500):
                ch = idl[i:i + 500]
                rows += db.execute("SELECT b.id,b.type,b.created_at,b.att_country,b.def_country,d.value FROM battles b "
                                   "JOIN battle_damage d ON d.battle_id=b.id AND d.etype=? AND d.eid=? "
                                   f"WHERE b.id IN ({','.join('?' * len(ch))})", (t, v, *ch)).fetchall()
            rows.sort(key=lambda r: -r[5])
            return ["battle", "type", "created", "attacker", "defender", f"{t}_damage"], [tuple(r) for r in rows[:top]], len(rows)
        rows = q(db, "SELECT id,type,created_at,att_country,def_country,att_damage+def_damage AS total,won_by FROM battles WHERE id IN ({IN}) ORDER BY total DESC", ids)
        hdr = ["battle", "type", "created", "attacker", "defender", "total_damage", "won_by"]
        return hdr, [tuple(r) for r in rows[:top]], len(rows)
    sel = {"user": f.user, "mu": f.mu, "country": f.country, "alliance": f.alliance}.get(by)
    sql = "SELECT eid,SUM(value) v,COUNT(*) n FROM battle_damage WHERE etype=? AND battle_id IN ({IN})"
    extra = [by]
    if sel:
        sql += " AND eid=?"; extra.append(sel)
    sql += " GROUP BY eid ORDER BY v DESC"
    # etype bound before IN list -> reorder params
    rows = []
    idl = list(ids)
    agg = defaultdict(lambda: [0.0, 0])
    for i in range(0, len(idl), 500):
        ch = idl[i:i + 500]
        s = f"SELECT eid,value FROM battle_damage WHERE etype=? AND battle_id IN ({','.join('?' * len(ch))})"
        p = [by, *ch]
        if sel:
            s += " AND eid=?"; p.append(sel)
        for r in db.execute(s, p):
            agg[r[0]][0] += r[1]; agg[r[0]][1] += 1
    rows = sorted(((k, v[0], v[1]) for k, v in agg.items()), key=lambda x: -x[1])
    return [by, "total_damage", "battles"], rows[:top], len(rows)


def orders(db, f, top=30):
    ids = battle_ids(db, f)
    rows = q(db, "SELECT o.battle_id,o.side,o.kind,o.eid,o.first_seen,b.att_country,b.def_country FROM orders o JOIN battles b ON b.id=o.battle_id WHERE o.battle_id IN ({IN})", ids)
    if f.country:
        rows = [r for r in rows if r["kind"] == "country" and r["eid"] == f.country]
    if f.mu:
        rows = [r for r in rows if r["kind"] == "mu" and r["eid"] == f.mu]
    cnt = defaultdict(lambda: [0, set()])
    for r in rows:
        k = (r["kind"], r["eid"], r["side"])
        cnt[k][0] += 1
    summ = sorted(((k[0], k[1], k[2], v[0]) for k, v in cnt.items()), key=lambda x: -x[3])
    return ["kind", "id", "side", "battles_ordered"], summ[:top], len(summ)


def bounty(db, f, top=20):
    """Bounty delta between the first and last snapshot inside the window (cumulative ranking values)."""
    s, e = f.since, f.until or "9999"
    out = []
    for rtype, sel in (("userBounty", f.user), ("muBounty", f.mu), ("countryBounty", f.country)):
        if (f.user or f.mu or f.country) and not sel:
            continue
        sql = "SELECT eid,ts,value FROM bounty_snap WHERE rtype=? AND ts>=? AND ts<?"
        p = [rtype, s, e]
        if sel:
            sql += " AND eid=?"; p.append(sel)
        by = defaultdict(list)
        for r in db.execute(sql + " ORDER BY ts", p):
            by[r["eid"]].append((r["ts"], r["value"]))
        for eid, pts in by.items():
            out.append((rtype, eid, pts[0][0][:16], pts[-1][0][:16], pts[0][1], pts[-1][1], pts[-1][1] - pts[0][1], len(pts)))
    out.sort(key=lambda r: -r[6])
    return ["ranking", "id", "first_snap", "last_snap", "first", "last", "delta", "snaps"], out[:top], len(out)


def contracts(db, f, top=20):
    sql, args = "SELECT * FROM contracts WHERE created_at>=?", [f.since]
    if f.until:
        sql += " AND created_at<?"; args.append(f.until)
    rows = db.execute(sql, args).fetchall()
    ids = battle_ids(db, Filters(f.since, f.until, f.alliance)) if f.alliance else None
    out = []
    for r in rows:
        bids = json.loads(r["bids_json"] or "[]")
        if f.country and f.country not in (r["country"], r["for_country"]):
            continue
        if f.mu and f.mu != r["winner_mu"] and f.mu not in {b.get("mu") for b in bids}:
            continue
        if f.user and f.user not in (r["created_by"], r["winner_user"]) and f.user not in {b.get("user") for b in bids}:
            continue
        if ids is not None and r["battle_id"] not in ids:
            continue
        out.append(r)
    st = defaultdict(lambda: [0, 0.0, 0.0])
    for r in out:
        x = st[r["status"]]; x[0] += 1; x[1] += r["budget"] or 0; x[2] += r["current_payout"] or 0
    summ = [(k, v[0], round(v[1], 2), round(v[2], 2)) for k, v in sorted(st.items(), key=lambda kv: -kv[1][0])]
    detail = [(r["id"], r["created_at"][:16], r["status"], r["for_country"], r["side"], r["min_damage"], r["budget"],
               r["current_payout"], r["winner_mu"], r["winner_user"]) for r in sorted(out, key=lambda r: r["created_at"], reverse=True)]
    return summ, detail


def fmt(v):
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) < 1000 else f"{v:,.0f}"
    if isinstance(v, int) and abs(v) >= 10000:
        return f"{v:,}"
    return str(v)


def table(hdr, rows, total=None, out=sys.stdout, as_csv=False):
    if as_csv:
        w = csv.writer(out); w.writerow(hdr); w.writerows(rows); return
    cells = [[fmt(v) for v in r] for r in rows]
    wd = [max(len(h), *(len(r[i]) for r in cells)) if cells else len(h) for i, h in enumerate(hdr)]
    print("  ".join(h.ljust(wd[i]) for i, h in enumerate(hdr)), file=out)
    for r in cells:
        print("  ".join(r[i].ljust(wd[i]) for i in range(len(hdr))), file=out)
    if total is not None and total > len(rows):
        print(f"... {total - len(rows)} more (use --top)", file=out)
