"""Validate one recorded session (a list of events) against the contract.

Result is pass/fail PER RULE plus an overall pass -- there is deliberately
no weighted conformance score. Rules:

  lifecycle_order      session_open first, deltas only inside their
                       begin..seal / begin..end window, nothing after a
                       terminal event, seq strictly increasing
  terminal_present     exactly the stream ends with a terminal event
  payload_schema       every event matches its per-type payload schema
  reference_integrity  THE one generic rule: no duplicate seq, no duplicate
                       begin for an id, no reference to an id never begun
  text_reassembly      stitched utterance chunks == the sealed final_text
  tool_args_reassembly stitched invocation arg chunks parse as JSON
  state_patch_chain    applying each patch to the last snapshot yields
                       the next snapshot
"""
import json
from dataclasses import dataclass, field

from .contract import TERMINAL_TYPES, schema_violations
from .statepatch import PatchError, apply_patch

RULES = ("lifecycle_order", "terminal_present", "payload_schema",
         "reference_integrity", "text_reassembly", "tool_args_reassembly",
         "state_patch_chain")


@dataclass
class RuleResult:
    passed: bool = True
    violations: list = field(default_factory=list)

    def fail(self, msg):
        self.passed = False
        self.violations.append(msg)

    def to_dict(self):
        return {"passed": self.passed, "violations": list(self.violations)}


@dataclass
class SessionReport:
    session_id: str = ""
    rules: dict = field(default_factory=lambda: {r: RuleResult() for r in RULES})

    @property
    def passed(self):
        return all(r.passed for r in self.rules.values())

    def to_dict(self):
        return {"passed": self.passed,
                "rules": {k: self.rules[k].to_dict() for k in sorted(self.rules)},
                "session_id": self.session_id}


def _seq(event):
    s = event.get("seq") if isinstance(event, dict) else None
    return s if isinstance(s, int) and not isinstance(s, bool) else None


def validate_session(events):
    if not isinstance(events, list):
        raise TypeError("a session is a list of events")
    rep = SessionReport()
    if events and isinstance(events[0], dict):
        rep.session_id = str(events[0].get("session_id", "") or "")
    life = rep.rules["lifecycle_order"]
    term = rep.rules["terminal_present"]
    schema = rep.rules["payload_schema"]
    refs = rep.rules["reference_integrity"]
    text_r = rep.rules["text_reassembly"]
    args_r = rep.rules["tool_args_reassembly"]
    state_r = rep.rules["state_patch_chain"]

    # --- payload schema -------------------------------------------------
    for ev in events:
        for v in schema_violations(ev):
            schema.fail(v)

    if not events:
        life.fail("empty stream: no session_open")
        term.fail("empty stream: no terminal event")
        return rep

    # --- lifecycle order ------------------------------------------------
    if events[0].get("type") != "session_open":
        life.fail("first event must be session_open, got %r" % events[0].get("type"))
    seqs = [_seq(e) for e in events]
    for prev, cur in zip(seqs, seqs[1:]):
        if prev is not None and cur is not None and cur <= prev:
            life.fail("seq must strictly increase (%s then %s)" % (prev, cur))
    terminal_seen = False
    open_utt, sealed_utt = set(), set()
    open_inv, ended_inv = set(), set()
    for ev in events:
        etype = ev.get("type")
        if terminal_seen:
            life.fail("event %r occurs after a terminal event" % etype)
        if etype in TERMINAL_TYPES:
            terminal_seen = True
        elif etype == "utterance_begin":
            open_utt.add(ev.get("utterance_id"))
        elif etype == "utterance_chunk":
            uid = ev.get("utterance_id")
            if uid not in open_utt:
                life.fail("utterance_chunk for %r before its utterance_begin" % uid)
            if uid in sealed_utt:
                life.fail("utterance_chunk for %r after its utterance_seal" % uid)
        elif etype == "utterance_seal":
            uid = ev.get("utterance_id")
            if uid not in open_utt:
                life.fail("utterance_seal for %r before its utterance_begin" % uid)
            sealed_utt.add(uid)
        elif etype == "invocation_begin":
            open_inv.add(ev.get("invocation_id"))
        elif etype == "invocation_args_chunk":
            iid = ev.get("invocation_id")
            if iid not in open_inv:
                life.fail("invocation_args_chunk for %r before its invocation_begin" % iid)
            if iid in ended_inv:
                life.fail("invocation_args_chunk for %r after its invocation_end" % iid)
        elif etype == "invocation_end":
            iid = ev.get("invocation_id")
            if iid not in open_inv:
                life.fail("invocation_end for %r before its invocation_begin" % iid)
            ended_inv.add(iid)

    # --- terminal present -------------------------------------------------
    if events[-1].get("type") not in TERMINAL_TYPES:
        term.fail("stream does not end with session_close or session_error")
    n_term = sum(1 for e in events if e.get("type") in TERMINAL_TYPES)
    if n_term > 1:
        term.fail("stream has %d terminal events, expected exactly 1" % n_term)

    # --- reference integrity (the single generic rule) --------------------
    seen_seq = set()
    for s in seqs:
        if s is not None:
            if s in seen_seq:
                refs.fail("duplicate seq %s" % s)
            seen_seq.add(s)
    begun_utt, begun_inv = set(), set()
    for ev in events:
        etype = ev.get("type")
        if etype == "utterance_begin":
            uid = ev.get("utterance_id")
            if uid in begun_utt:
                refs.fail("duplicate utterance_begin for %r" % uid)
            begun_utt.add(uid)
        elif etype == "invocation_begin":
            iid = ev.get("invocation_id")
            if iid in begun_inv:
                refs.fail("duplicate invocation_begin for %r" % iid)
            begun_inv.add(iid)
    for ev in events:
        etype = ev.get("type")
        if etype in ("utterance_chunk", "utterance_seal") \
                and ev.get("utterance_id") not in begun_utt:
            refs.fail("%s references utterance %r that is never begun"
                      % (etype, ev.get("utterance_id")))
        if etype in ("invocation_args_chunk", "invocation_end") \
                and ev.get("invocation_id") not in begun_inv:
            refs.fail("%s references invocation %r that is never begun"
                      % (etype, ev.get("invocation_id")))

    # --- text reassembly --------------------------------------------------
    chunks = {}
    for ev in events:
        if ev.get("type") == "utterance_chunk" and isinstance(ev.get("delta"), str):
            chunks.setdefault(ev.get("utterance_id"), []).append(ev["delta"])
    for ev in events:
        if ev.get("type") == "utterance_seal":
            uid = ev.get("utterance_id")
            stitched = "".join(chunks.get(uid, []))
            if stitched != ev.get("final_text"):
                text_r.fail("utterance %r: stitched chunks %r != final_text %r"
                            % (uid, stitched, ev.get("final_text")))

    # --- tool-args reassembly ---------------------------------------------
    arg_chunks = {}
    for ev in events:
        if ev.get("type") == "invocation_args_chunk" \
                and isinstance(ev.get("args_delta"), str):
            arg_chunks.setdefault(ev.get("invocation_id"), []).append(ev["args_delta"])
    for ev in events:
        if ev.get("type") == "invocation_end":
            iid = ev.get("invocation_id")
            raw = "".join(arg_chunks.get(iid, []))
            try:
                json.loads(raw)
            except Exception as exc:
                args_r.fail("invocation %r: reassembled args do not parse as JSON (%s)"
                            % (iid, exc))

    # --- state patch chain --------------------------------------------------
    current = None
    pending_patch = None
    for ev in events:
        etype = ev.get("type")
        if etype == "state_full":
            snap = ev.get("state")
            if pending_patch is not None and current is not None:
                try:
                    expected = apply_patch(current, pending_patch)
                except PatchError as exc:
                    state_r.fail("state_patch cannot be applied: %s" % exc)
                    expected = None
                if expected is not None and expected != snap:
                    state_r.fail("applying the patch to the previous snapshot "
                                 "does not produce the next snapshot")
            elif pending_patch is not None and current is None:
                state_r.fail("state_patch appears before any state_full snapshot")
            if isinstance(snap, dict):
                current = snap
            pending_patch = None
        elif etype == "state_patch":
            if current is None:
                state_r.fail("state_patch appears before any state_full snapshot")
            pending_patch = ev.get("patch")
    return rep


def validate_sessions(sessions):
    """sessions: {name: events} -> {name: SessionReport}"""
    return {name: validate_session(evs) for name, evs in sessions.items()}


def sessions_passing(reports):
    return sum(1 for r in reports.values() if r.passed)
