#!/usr/bin/env python3
"""Deterministic golden evals over the planted corpus.

Writes evals/eval_report.json byte-stable (sort_keys, indent=2, no timestamps).
Each broken stream must fail exactly its planted rule; each clean stream
must pass every rule.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_event_contract.cli import discover
from ui_event_contract.streams import BROKEN
from ui_event_contract.validator import sessions_passing, validate_session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STREAMS = os.path.join(ROOT, "fixtures", "streams")
# fixture file names use hyphens; BROKEN keys use underscores
EXPECTED = {k.replace("_", "-"): v[1] for k, v in BROKEN.items()}


def main():
    sessions = discover(STREAMS)
    cases = {}
    passing = 0
    for name, events in sessions:
        rep = validate_session(events)
        failed = sorted(r for r in rep.rules if not rep.rules[r].passed)
        if name in EXPECTED:
            ok = failed == [EXPECTED[name]]
            cases[name] = {"detected": EXPECTED[name] in failed,
                           "expected_rule": EXPECTED[name],
                           "failed_rules": failed, "isolated": ok,
                           "kind": "broken"}
        else:
            ok = rep.passed
            cases[name] = {"detected": rep.passed, "expected_rule": None,
                           "failed_rules": failed, "isolated": ok,
                           "kind": "clean"}
        if rep.passed:
            passing += 1
    broken_ok = sum(1 for n, c in cases.items()
                    if c["kind"] == "broken" and c["detected"])
    clean_ok = sum(1 for n, c in cases.items()
                   if c["kind"] == "clean" and c["detected"])
    report = {
        "cases": cases,
        "summary": {
            "broken_detected": broken_ok,
            "broken_total": len(EXPECTED),
            "clean_passing": clean_ok,
            "clean_total": sum(1 for c in cases.values() if c["kind"] == "clean"),
            "sessions_passing": passing,
            "sessions_total": len(sessions),
        },
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_report.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("broken %d/%d  clean %d/%d  sessions passing %d/%d"
          % (broken_ok, len(EXPECTED), clean_ok, report["summary"]["clean_total"],
             passing, len(sessions)))
    print("Wrote %s" % out)
    perfect = (broken_ok == len(EXPECTED)
               and clean_ok == report["summary"]["clean_total"]
               and all(c["isolated"] for c in cases.values()))
    return 0 if perfect else 1


if __name__ == "__main__":
    raise SystemExit(main())
