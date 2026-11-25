"""Minimal rate-limited client for the WarEra tRPC API (GET, JSON input in query string)."""
import json, os, time, urllib.parse, urllib.request, urllib.error, collections

BASE = "https://api2.warera.io/trpc/"


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
        url = BASE + proc
        if params:
            url += "?" + urllib.parse.urlencode({"input": json.dumps(params, separators=(",", ":"))})
        for attempt in range(5):
            self._throttle()
            self.n += 1
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=self._headers()), timeout=self.timeout) as r:
                    return json.loads(r.read())["result"]["data"]
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:
                    time.sleep(5 * (attempt + 1)); continue
                try:
                    msg = json.loads(e.read())["error"]["message"]
                except Exception:
                    msg = str(e)
                raise ApiError(f"{proc} {params}: HTTP {e.code} {msg}")
            except (urllib.error.URLError, TimeoutError):
                time.sleep(3 * (attempt + 1))
        raise ApiError(f"{proc}: gave up after retries")

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
