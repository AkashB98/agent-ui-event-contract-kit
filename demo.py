#!/usr/bin/env python3
"""End-to-end demo: validate the planted corpus and summarise. Exit 0 on success."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ui_event_contract.cli import discover, DEFAULT_STREAMS
from ui_event_contract.streams import BROKEN
from ui_event_contract.validator import sessions_passing, validate_session


def main():
    sessions = discover(DEFAULT_STREAMS)
    print("Demo: validating %d planted streams" % len(sessions))
    ok = True
    reports = {}
    for name, events in sessions:
        rep = validate_session(events)
        reports[name] = rep
        failed = [r for r in sorted(rep.rules) if not rep.rules[r].passed]
        print("  %s: %s" % (name, "PASS" if rep.passed else "FAIL " + ",".join(failed)))
        if name.startswith("clean-") or name.startswith("clean_"):
            if not rep.passed:
                ok = False
        if name in BROKEN:
            expected = BROKEN[name][1]
            if rep.rules[expected].passed:
                ok = False
                print("    !! expected rule %s to fail" % expected)
    print("Sessions passing: %d/%d" % (sessions_passing(reports), len(reports)))
    print("Demo result:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
