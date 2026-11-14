"""CLI: check / demo / serve. Stdlib only."""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from .streams import all_sessions
from .validator import sessions_passing, validate_session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STREAMS = os.path.join(ROOT, "fixtures", "streams")


def load_jsonl(path):
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def discover(path):
    """Return [(name, events)] for a .jsonl file or a directory of them."""
    if os.path.isfile(path):
        return [(os.path.splitext(os.path.basename(path))[0], load_jsonl(path))]
    if os.path.isdir(path):
        out = []
        for name in sorted(os.listdir(path)):
            if name.endswith(".jsonl"):
                out.append((os.path.splitext(name)[0],
                            load_jsonl(os.path.join(path, name))))
        return out
    return []


def format_report(name, report):
    lines = ["%s: %s" % (name, "PASS" if report.passed else "FAIL")]
    for rule in sorted(report.rules):
        r = report.rules[rule]
        lines.append("  %s: %s" % (rule, "pass" if r.passed else "FAIL"))
        for v in r.violations:
            lines.append("    - %s" % v)
    return "\n".join(lines)


def cmd_check(args):
    sessions = discover(args.path)
    if not sessions:
        print("No .jsonl streams found at %s" % args.path)
        return 2
    reports = {}
    for name, events in sessions:
        rep = validate_session(events)
        reports[name] = rep
        print(format_report(name, rep))
    print("Sessions passing: %d/%d" % (sessions_passing(reports), len(reports)))
    return 0 if sessions_passing(reports) == len(reports) else 1


def cmd_demo(args):
    sys.path.insert(0, ROOT)
    import demo as demo_mod
    return demo_mod.main()


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass

        def do_GET(self):
            if self.path == "/health":
                payload = b'{"status": "ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers(); self.wfile.write(payload); return
            self.send_response(404); self.end_headers()

        def do_POST(self):
            if self.path != "/validate":
                self.send_response(404); self.end_headers(); return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                spec = json.loads(raw.decode("utf-8"))
                events = spec["events"]
            except Exception:
                self.send_response(400); self.end_headers()
                self.wfile.write(b'{"error": "expected JSON with an events list"}')
                return
            payload = json.dumps(validate_session(events).to_dict(),
                                 sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
    return Handler


def cmd_serve(args):
    server = HTTPServer((args.host, args.port), make_handler())
    print("Serving on http://%s:%d (POST /validate, GET /health)"
          % (args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="ui-event-contract",
                                description="Agent-to-frontend event-stream contract validator")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("check")
    sp.add_argument("path", nargs="?", default=DEFAULT_STREAMS)
    sub.add_parser("demo")
    sp = sub.add_parser("serve")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "demo":
        return cmd_demo(args)
    if args.cmd == "serve":
        return cmd_serve(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
