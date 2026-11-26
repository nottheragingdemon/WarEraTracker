"""Minimal rate-limited client for the WarEra tRPC API (GET, JSON input in query string)."""
import json, os, time, threading, urllib.parse, urllib.request, urllib.error, collections
from concurrent.futures import ThreadPoolExecutor

try:   # the project's own aiohttp client (wartrack/async_requests.py); plain urllib is the fallback if aiohttp is missing
    from .async_requests import AsyncHTTPClient
except ImportError:   # pragma: no cover
    AsyncHTTPClient = None


GW_UNSUPPORTED = {"ranking.getRankingPage", "alliance.getManyPaginated", "employee.getCompanyEstimate"}   # seen refused by the gateway (HTTP 400 unknown method)
BASE = "https://api2.warera.io/trpc/"
GATEWAY = "https://gateway.warerastats.io/trpc/"  # community cache/proxy (warerastats.io); needs the same API key, falls back to BASE


class ApiError(Exception):
    pass


def _body(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return None


def load_key():
    """API key from $WARERA_API_KEY or a .env file in the project root (never commit it)."""
    k = os.environ.get("WARERA_API_KEY")
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not k and os.path.exists(env):
        for line in open(env):
            if line.startswith("WARERA_API_KEY="):
                k = line.split("=", 1)[1].strip().strip("'\"")
    return k or None


class Client:
    def __init__(self, max_calls=None, window=60.0, timeout=30, verbose=False, key="auto", workers=6):
        self.key = load_key() if key == "auto" else key
        # documented limits: 100/min without a key, 500/min with one; stay a little under
        self.max_calls = max_calls or (450 if self.key else 90)
        self.window, self.timeout, self.verbose, self.workers = window, timeout, verbose, workers
        self._calls = collections.deque()
        self._lock = threading.Lock()
        self.n = 0
        # gateway first (cached, de-duplicated), official API as the fallback; WARERA_GATEWAY=0 turns it off
        self.use_gateway = bool(self.key) and os.environ.get("WARERA_GATEWAY", "1") != "0"
        self.gw_fail = 0
        self.gw_skip = set(GW_UNSUPPORTED)   # procedures the gateway is known not to serve go straight to the official API
        self.gw_served = 0

    def _headers(self):
        h = {"User-Agent": "wartrack/0.3"}
        if self.key:
            h["X-API-Key"] = self.key
        return h

    def _fetch_many(self, urls):
        """GET all urls at once -> [(status, body)]; status 0 = network error or timeout; body is parsed JSON, text or None"""
        h = self._headers()
        if AsyncHTTPClient:
            res = AsyncHTTPClient(timeout=self.timeout, max_concurrent=len(urls)).execute(
                [{"_id": i, "method": "get", "url": u, "headers": h} for i, u in enumerate(urls)])
            return [(r["status_code"] or 0, r["body"]) for r in res]
        out = []
        for u in urls:
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=self.timeout) as r:
                    out.append((r.status, _body(r.read())))
            except urllib.error.HTTPError as e:
                out.append((e.code, _body(e.read())))
            except Exception:
                out.append((0, None))
        return out

    def _gw_reject(self, what, code, body):
        new = [w for w in what if w not in self.gw_skip]
        self.gw_skip.update(what)
        if not new:       # another thread already reported it
            return
        print(f"  [gateway] {', '.join(what)[:50]}: HTTP {code} {str(body)[:160]!r}; this goes to the official API", flush=True)

    def _gw_error(self, names, body):
        """The gateway answered 200 with an error inside. A backend failure (HTTP 5xx inside) is temporary: count it and retry on the
        official API. Anything else means it doesn't serve this procedure: skip it for the rest of the run."""
        e = (body or {}).get("error") or {}
        status = ((e.get("data") or {}).get("httpStatus")) or 0
        if status >= 500 or e.get("code") == -32603:
            self._gw_bad("gateway backend error"); return "official", 0
        self._gw_reject(names, 200, body); return "again", 0

    def _gw_bad(self, why):
        self.gw_fail += 1
        if self.use_gateway and self.gw_fail >= 3:
            self.use_gateway = False
            print(f"  [gateway] {why}; using the official API for the rest of this run", flush=True)

    def _throttle(self):
        with self._lock:      # threads queue here, so the per-minute budget is shared by all of them
            now = time.monotonic()
            while self._calls and now - self._calls[0] > self.window:
                self._calls.popleft()
            if len(self._calls) >= self.max_calls:
                wait = self.window - (now - self._calls[0]) + 0.2
                if self.verbose:
                    print(f"  [rate limit] sleeping {wait:.0f}s", flush=True)
                time.sleep(max(wait, 0))
            self._calls.append(time.monotonic())
            self.n += 1

    def _judge(self, names, gw, status, body, batch):
        """Look at one reply -> ("ok", data) or ("again", seconds to wait first); raises ApiError on a real client error."""
        good = isinstance(body, (dict, list))
        if status == 200 and good:
            if not batch:
                if gw and "result" not in body:
                    return self._gw_error(names, body)
                if gw:
                    self.gw_served += 1
                return "ok", body["result"]["data"]
            body = body if isinstance(body, list) else [body]
            if gw and len(body) != len(names):
                self._gw_bad("gateway batch failed"); return "again", 0
            if gw and all("error" in x for x in body):
                return self._gw_error(names, body[0])
            if gw:
                self.gw_served += 1
            return "ok", [None if "error" in x else x["result"]["data"] for x in body]
        if status == 0 or status == 200:        # unreachable, timeout or an unreadable reply
            if gw:
                self._gw_bad("gateway unreachable"); return "again", 0
            return "again", 3
        if gw:
            if 400 <= status < 500 and status != 429:
                self._gw_reject(names, status, body)
            else:
                self._gw_bad(f"HTTP {status}")
            return "again", 0
        if status == 429 or status >= 500:
            return "again", 5
        msg = ""
        try:
            msg = body["error"]["message"]
        except Exception:
            msg = f"HTTP {status}"
        raise ApiError(f"{','.join(names)[:60]}: HTTP {status} {msg}")

    def _call_url(self, proc, params, official=False):
        gw = self.use_gateway and not official and proc not in self.gw_skip
        tail = proc + ("?" + urllib.parse.urlencode({"input": json.dumps(params, separators=(",", ":"))}) if params else "")
        return gw, (GATEWAY if gw else BASE) + tail

    def call(self, proc, **params):
        params = {k: v for k, v in params.items() if v is not None}
        force = False
        for attempt in range(5):
            self._throttle()
            gw, url = self._call_url(proc, params, force)
            status, body = self._fetch_many([url])[0]
            kind, val = self._judge([proc], gw, status, body, False)
            if kind == "ok":
                return val
            force = kind == "official"
            if val:
                time.sleep(val * (attempt + 1))
        raise ApiError(f"{proc}: gave up after retries")

    def _batch_url(self, calls, official):
        names = ",".join(c[0] for c in calls)
        inp = {str(i): ({k: v for k, v in c[1].items() if v is not None} if c[1] else {}) for i, c in enumerate(calls)}
        gw = self.use_gateway and not official and not any(c[0] in self.gw_skip for c in calls)
        return gw, (GATEWAY if gw else BASE) + names + "?batch=1&input=" + urllib.parse.quote(json.dumps(inp, separators=(",", ":")))

    def batch(self, calls, official=False):
        """One HTTP request for several procedures: [(proc, params), ...] -> [data or None]. Failed entries give None."""
        if not calls:
            return []
        names = [c[0] for c in calls]
        force = False
        for attempt in range(5):
            self._throttle()
            gw, url = self._batch_url(calls, official or force)
            status, body = self._fetch_many([url])[0]
            kind, val = self._judge(names, gw, status, body, True)
            if kind == "ok":
                return val
            force = kind == "official"
            if val:
                time.sleep(val * (attempt + 1))
        raise ApiError("batch: gave up after retries")

    def batch_many(self, call_lists, official=False, group=8):
        """Several batch requests in flight at once through the async client: [[(proc, params), ...], ...] -> [[data or None], ...].
        Requests that don't come back clean are retried together, in further parallel rounds, so one slow or failing request
        never holds up the others."""
        call_lists = list(call_lists)
        out = [None] * len(call_lists)
        force = set()
        for g in range(0, len(call_lists), group):
            todo = list(range(g, min(g + group, len(call_lists))))
            for attempt in range(5):
                if not todo:
                    break
                urls = []
                for i in todo:
                    self._throttle()
                    urls.append(self._batch_url(call_lists[i], official or i in force))
                replies = self._fetch_many([u for _, u in urls])
                again, wait = [], 0
                for i, (gw, _), (status, body) in zip(todo, urls, replies):
                    kind, val = self._judge([c[0] for c in call_lists[i]], gw, status, body, True)
                    if kind == "ok":
                        out[i] = val
                    else:
                        again.append(i); wait = max(wait, val)
                        if kind == "official":
                            force.add(i)
                todo = again
                if todo and wait:
                    time.sleep(wait * (attempt + 1))
            if todo:
                raise ApiError("batch: gave up after retries")
        return out

    def map(self, fn, items, workers=None):
        """fn(item) for every item, several at a time (results in input order). The shared throttle keeps the call rate in budget."""
        items = list(items)
        if len(items) <= 1:
            return [fn(x) for x in items]
        with ThreadPoolExecutor(max_workers=min(workers or self.workers, len(items))) as ex:
            return list(ex.map(fn, items))

    def lookup_users(self, ids, chunk=40):
        """{user id: getUserLite data} for the ids that answered, fetched in parallel batches"""
        ids = list(ids)
        chunks = [ids[i:i + chunk] for i in range(0, len(ids), chunk)]
        out = {}
        for ch, res in zip(chunks, self.batch_many([[("user.getUserLite", {"userId": u}) for u in ch] for ch in chunks])):
            out.update({u: d for u, d in zip(ch, res) if d})
        return out

    def pages(self, proc, max_pages=1000, **params):
        """Yield items across cursor pages."""
        cursor = None
        for _ in range(max_pages):
            d = self.call(proc, cursor=cursor, **params)
            items = d["items"] if isinstance(d, dict) else d
            yield from items
            cursor = d.get("nextCursor") if isinstance(d, dict) else None
            if not cursor or not items:
                return
