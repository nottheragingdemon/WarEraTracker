"""Minimal rate-limited client for the WarEra tRPC API (GET, JSON input in query string)."""
import json, os, time, urllib.parse, urllib.request, urllib.error, collections

BASE = "https://api2.warera.io/trpc/"
GATEWAY = "https://gateway.warerastats.io/trpc/"  # community cache/proxy (warerastats.io); needs the same API key, falls back to BASE


class ApiError(Exception):
    pass


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
    def __init__(self, max_calls=None, window=60.0, timeout=30, verbose=False, key="auto"):
        self.key = load_key() if key == "auto" else key
        # documented limits: 100/min without a key, 500/min with one; stay a little under
        self.max_calls = max_calls or (450 if self.key else 90)
        self.window, self.timeout, self.verbose = window, timeout, verbose
        self._calls = collections.deque()
        self.n = 0
        # gateway first (cached, de-duplicated), official API as the fallback; WARERA_GATEWAY=0 turns it off
        self.use_gateway = bool(self.key) and os.environ.get("WARERA_GATEWAY", "1") != "0"
        self.gw_fail = 0
        self.gw_served = 0

    def _base(self):
        return GATEWAY if self.use_gateway else BASE

    def _gw_bad(self, why):
        self.gw_fail += 1
        if self.use_gateway and self.gw_fail >= 3:
            self.use_gateway = False
            print(f"  [gateway] {why}; using the official API for the rest of this run", flush=True)

    def _headers(self):
        h = {"User-Agent": "wartrack/0.2"}
        if self.key:
            h["X-API-Key"] = self.key
        return h

    def _throttle(self):
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.window:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            wait = self.window - (now - self._calls[0]) + 0.2
            if self.verbose:
                print(f"  [rate limit] sleeping {wait:.0f}s", flush=True)
            time.sleep(max(wait, 0))
        self._calls.append(time.monotonic())

    def call(self, proc, **params):
        params = {k: v for k, v in params.items() if v is not None}
        tail = proc
        if params:
            tail += "?" + urllib.parse.urlencode({"input": json.dumps(params, separators=(",", ":"))})
        for attempt in range(5):
            self._throttle()
            self.n += 1
            gw = self.use_gateway
            url = self._base() + tail
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=self._headers()), timeout=self.timeout) as r:
                    j = json.loads(r.read())
                if gw and ("result" not in j):
                    self._gw_bad("gateway returned an error"); continue
                if gw:
                    self.gw_served += 1
                return j["result"]["data"]
            except urllib.error.HTTPError as e:
                if gw:
                    self._gw_bad(f"HTTP {e.code}"); continue
                if e.code == 429 or e.code >= 500:
                    time.sleep(5 * (attempt + 1)); continue
                try:
                    msg = json.loads(e.read())["error"]["message"]
                except Exception:
                    msg = str(e)
                raise ApiError(f"{proc} {params}: HTTP {e.code} {msg}")
            except (urllib.error.URLError, TimeoutError, ValueError):
                if gw:
                    self._gw_bad("gateway unreachable"); continue
                time.sleep(3 * (attempt + 1))
        raise ApiError(f"{proc}: gave up after retries")

    def batch(self, calls, official=False):
        """One HTTP request for several procedures: [(proc, params), ...] -> [data or None]. Failed entries give None."""
        if not calls:
            return []
        names = ",".join(c[0] for c in calls)
        inp = {str(i): ({k: v for k, v in c[1].items() if v is not None} if c[1] else {}) for i, c in enumerate(calls)}
        tail = names + "?batch=1&input=" + urllib.parse.quote(json.dumps(inp, separators=(",", ":")))
        for attempt in range(5):
            self._throttle()
            self.n += 1
            gw = self.use_gateway and not official
            url = (GATEWAY if gw else BASE) + tail
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=self._headers()), timeout=self.timeout) as r:
                    j = json.loads(r.read())
                j = j if isinstance(j, list) else [j]
                if gw and (len(j) != len(calls) or all("error" in x for x in j)):
                    self._gw_bad("gateway batch failed"); continue
                if gw:
                    self.gw_served += 1
                return [None if "error" in x else x["result"]["data"] for x in j]
            except urllib.error.HTTPError as e:
                if gw:
                    self._gw_bad(f"HTTP {e.code}"); continue
                if e.code == 429 or e.code >= 500:
                    time.sleep(5 * (attempt + 1)); continue
                raise ApiError(f"batch {names[:60]}: HTTP {e.code}")
            except (urllib.error.URLError, TimeoutError, ValueError):
                if gw:
                    self._gw_bad("gateway unreachable"); continue
                time.sleep(3 * (attempt + 1))
        raise ApiError("batch: gave up after retries")

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
