"""The Company tax page's conquered-region split, run in headless Chrome on a small made-up data set (skipped without Chrome).

Host Aland holds R1 (its own) and R2 (conquered from Bland). Income tax 10%, manager tax 0%, core share 10%:
R1 pays 100 wages/h -> 10 tax; R2 pays 50 -> 5 tax, of which 0.5 goes to Bland. Aland keeps 14.5 of 15."""
import http.server, json, os, re, shutil, subprocess, tempfile, threading, time, unittest

SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site")
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


def fixture():
    now = int(time.time() * 1000)
    ents = [["country", "A", "Aland"], ["country", "B", "Bland"], ["alliance", "EA", "The Emerald Accord"], ["user", "u1", "Ann"], ["user", "u2", "Bob"]]
    data = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "ents": ents, "alliances": {"2": [0]},
            "regionsNow": {"r1": ["R1", 0, 10.0, 0.0, 1, 3, 0], "r2": ["R2", 0, 4.5, 0.0, 1, 2, 1]},
            "countryTax": {"0": [10, 0]}, "rateHist": {"0": [[now - 7200000, 10, 0]]}, "runs": [now - 7200000, now - 3600000],
            "countryNow": {"0": [1000, 0, 1, 10, 1, {"employeeIncomeTax": 14.5, "total": 14.5}]}, "coreTaxPct": 10}
    comp = {"companies": [["C1", 3, "bread", 1, "r1", 0, 3, 100.0, 0.0], ["C2", 4, "bread", 1, "r2", 1, 2, 50.0, 0.0]],
            "wageHist": [[0, 0, now - 7200000, 1, 3, 100.0, 0.0, 0], [0, 1, now - 7200000, 1, 2, 50.0, 0.0, 1]], "wageHistReg": []}
    return data, comp


@unittest.skipUnless(CHROME, "needs Chrome")
class CompanyPageTests(unittest.TestCase):
    def test_conquered_split(self):
        tmp = tempfile.mkdtemp()
        try:
            for f in ("company.html", "theme.js", "theme.css"):
                shutil.copy(os.path.join(SITE, f), tmp)
            data, comp = fixture()
            json.dump(data, open(os.path.join(tmp, "data.json"), "w"))
            json.dump(comp, open(os.path.join(tmp, "company-data.json"), "w"))
            handler = lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=tmp)
            http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            dom = subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=6000", "--dump-dom",
                                  f"http://127.0.0.1:{srv.server_address[1]}/company.html"], capture_output=True, text=True, timeout=120).stdout
            srv.shutdown()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        text = re.sub(r"<[^>]+>", " ", dom)
        text = re.sub(r"\s+", " ", text)
        self.assertIn("conquered from Bland", text)                                  # region picker label
        self.assertRegex(text, r"Total 15\.0000")
        self.assertRegex(text, r"Passed to Bland \(10% of the tax from R2\) 0\.5000")
        self.assertRegex(text, r"Aland keeps 14\.5000")
        self.assertRegex(text, r"14\.5000 /h of the 15\.0000 /h")


if __name__ == "__main__":
    unittest.main()
