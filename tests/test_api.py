"""Offline tests for the API client against a local fake tRPC server (no network, no API key)."""
import json, threading, unittest, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from wartrack import api

HITS = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        side, rest = u.path.split("/trpc/")[0].strip("/"), u.path.split("/trpc/")[1]
        procs = rest.split(",")
        q = urllib.parse.parse_qs(u.query)
        inp = json.loads(q["input"][0]) if "input" in q else {}
        HITS.append((side, rest))
        if side == "gw" and any(p == "only.official" for p in procs):
            return self.reply(404, {"error": {"message": "not on gateway"}})
        if "flaky" in rest and sum(1 for h in HITS if "flaky" in h[1] and h[0] == side) < 2:
            return self.reply(500, {"error": {"message": "boom"}})
        if side == "gw" and rest == "gw.backend.down":
            return self.reply(200, {"error": {"code": -32603, "data": {"httpStatus": 500}, "message": "db down"}})
        if side == "gw" and rest == "gw.unknown":
            return self.reply(200, {"error": {"code": -32004, "data": {"httpStatus": 404}, "message": "no such"}})
        if "batch" in q and "gone.company" in rest:   # tRPC answers 207 when some entries of a batch fail
            body = [{"result": {"data": {"p": "ok"}}} if p != "gone.company" else {"error": {"message": "not found"}} for p in procs]
            return self.reply(207, body)
        if rest == "client.error":
            return self.reply(400, {"error": {"message": "bad input"}})

        def one(p, i):
            if p == "bad.proc":
                return {"error": {"message": "x"}}
            if p == "user.getUserLite":
                return {"result": {"data": {"username": "u" + i["userId"], "country": "c1"}}}
            if p == "pg":
                cur = i.get("cursor") or 0
                return {"result": {"data": {"items": [cur * 2, cur * 2 + 1], "nextCursor": cur + 1 if cur < 2 else None}}}
            return {"result": {"data": {"p": p, "side": side}}}
        out = [one(p, inp.get(str(k), {})) for k, p in enumerate(procs)] if "batch" in q else one(procs[0], inp)
        self.reply(200, out)

    def reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.old = (api.BASE, api.GATEWAY)
        api.BASE, api.GATEWAY = base + "/api/trpc/", base + "/gw/trpc/"

    @classmethod
    def tearDownClass(cls):
        api.BASE, api.GATEWAY = cls.old
        cls.srv.shutdown()

    def setUp(self):
        HITS.clear()
        self.c = api.Client(key=None)

    def test_call(self):
        self.assertEqual(self.c.call("x.y", a=1)["p"], "x.y")

    def test_client_error_raises(self):
        with self.assertRaises(api.ApiError):
            self.c.call("client.error")

    def test_batch_marks_failed_entries_none(self):
        self.assertEqual(self.c.batch([("x.a", {}), ("bad.proc", {})]), [{"p": "x.a", "side": "api"}, None])

    def test_lookup_users_many_chunks(self):
        got = self.c.lookup_users([str(i) for i in range(500)])
        self.assertEqual(len(got), 500)
        self.assertEqual(got["99"]["username"], "u99")

    def test_pages_follow_cursors(self):
        self.assertEqual(list(self.c.pages("pg")), [0, 1, 2, 3, 4, 5])

    def test_map_keeps_order(self):
        self.assertEqual(self.c.map(lambda x: x * 2, [3, 1, 2]), [6, 2, 4])

    def test_server_error_is_retried(self):
        self.c.window = 60
        import time
        orig, time.sleep = time.sleep, lambda s: None
        try:
            self.assertEqual(self.c.call("flaky.proc")["p"], "flaky.proc")
        finally:
            time.sleep = orig

    def test_gateway_first_then_official_fallback(self):
        c = api.Client(key="k")
        self.assertEqual(c.call("x.y")["side"], "gw")
        self.assertEqual(c.call("only.official")["side"], "api")
        self.assertIn("only.official", c.gw_skip)
        HITS.clear()
        c.call("only.official")
        self.assertEqual([h[0] for h in HITS], ["api"])      # remembered: no second gateway attempt
        self.assertEqual(c.call("x.y")["side"], "gw")        # other procedures still use the gateway

    def test_gateway_backend_error_is_temporary_but_unknown_is_skipped(self):
        c = api.Client(key="k")
        self.assertEqual(c.call("gw.backend.down")["side"], "api")
        self.assertNotIn("gw.backend.down", c.gw_skip)
        self.assertEqual(c.gw_fail, 1)
        self.assertEqual(c.call("gw.unknown")["side"], "api")
        self.assertIn("gw.unknown", c.gw_skip)

    def test_gateway_rests_after_failures_then_returns(self):
        import time
        c = api.Client(key="k")
        c.gw_cooldown = 0.3
        for _ in range(3):
            c.call("gw.backend.down")
        self.assertFalse(c.use_gateway)
        time.sleep(0.4)
        self.assertTrue(c.use_gateway)
        self.assertEqual(c.call("x.y")["side"], "gw")

    def test_batch_207_partial_failure(self):
        self.assertEqual(self.c.batch([("x.a", {}), ("gone.company", {})]), [{"p": "ok"}, None])
        self.assertEqual(self.c.batch_many([[("x.a", {}), ("gone.company", {})]]), [[{"p": "ok"}, None]])

    def test_batch_many_matches_batch(self):
        lists = [[("x.a", {}), ("x.b", {})] for _ in range(20)]
        self.assertEqual(self.c.batch_many(lists), [self.c.batch(l) for l in lists])


    def test_only_failed_requests_are_retried(self):
        import time
        HITS.clear()
        c = self.c
        orig, time.sleep = time.sleep, lambda s: None
        try:
            lists = [[("x.a", {})], [("flaky.two", {})], [("x.b", {})]]
            out = c.batch_many(lists)
        finally:
            time.sleep = orig
        self.assertEqual([o[0]["p"] for o in out], ["x.a", "flaky.two", "x.b"])
        self.assertEqual(sum(1 for h in HITS if h[1].startswith("x.")), 2)   # the good ones were fetched once


class ImportTests(unittest.TestCase):
    def test_modules_import(self):
        import wartrack.collect, wartrack.alerts, wartrack.export, wartrack.db   # noqa: F401
        self.assertTrue(issubclass(api.ApiError, Exception))
        self.assertTrue(api.BASE.startswith("http"))


if __name__ == "__main__":
    unittest.main()
