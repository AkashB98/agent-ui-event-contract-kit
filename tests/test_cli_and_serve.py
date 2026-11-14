import json, os, sys, threading, unittest, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from http.server import HTTPServer
from ui_event_contract.cli import discover, load_jsonl, main, make_handler
from ui_event_contract.streams import clean_text_only

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STREAMS = os.path.join(ROOT, "fixtures", "streams")

class TestCli(unittest.TestCase):
    def test_discover_dir(self):
        s = discover(STREAMS); self.assertEqual(len(s), 10)
    def test_discover_file(self):
        s = discover(os.path.join(STREAMS, "clean-text-only.jsonl"))
        self.assertEqual(len(s), 1); self.assertEqual(s[0][0], "clean-text-only")
    def test_discover_missing(self): self.assertEqual(discover("/nope/x"), [])
    def test_load_jsonl_roundtrip(self):
        evs = load_jsonl(os.path.join(STREAMS, "clean-text-only.jsonl"))
        self.assertEqual(evs[0]["type"], "session_open")
    def test_check_clean_file_exit_0(self):
        self.assertEqual(main(["check", os.path.join(STREAMS, "clean-text-only.jsonl")]), 0)
    def test_check_broken_file_exit_1(self):
        self.assertEqual(main(["check", os.path.join(STREAMS, "broken-state-patch.jsonl")]), 1)
    def test_check_missing_exit_2(self):
        self.assertEqual(main(["check", "/nope"]), 2)
    def test_demo_exit_0(self): self.assertEqual(main(["demo"]), 0)

class TestServe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), make_handler())
        cls.port = cls.server.server_address[1]
        cls.t = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.t.start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown()
    def _get(self, path):
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, path)) as r:
            return r.status, json.loads(r.read())
    def _post(self, payload):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/validate" % self.port,
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    def test_health(self):
        status, body = self._get("/health"); self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
    def test_validate_clean(self):
        status, body = self._post({"events": clean_text_only()})
        self.assertEqual(status, 200); self.assertTrue(body["passed"])
    def test_validate_broken(self):
        evs = clean_text_only(); evs.pop()  # drop terminal
        status, body = self._post({"events": evs})
        self.assertFalse(body["passed"])
        self.assertFalse(body["rules"]["terminal_present"]["passed"])

if __name__ == "__main__":
    unittest.main()
