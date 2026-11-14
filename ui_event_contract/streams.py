"""Deterministic planted streams: clean sessions + one defect per class.

Synthetic only. Chunk splits use fixed size cycles, so output is
byte-stable with no randomness and no network.
"""
import json

SIZES = (4, 3, 5, 2, 6)


def _chunks(text):
    out, i, k = [], 0, 0
    while i < len(text):
        n = SIZES[k % len(SIZES)]
        out.append(text[i:i + n])
        i += n
        k += 1
    return out or [""]


class Builder:
    def __init__(self, session_id):
        self.session_id = session_id
        self.events = []
        self._seq = 0

    def add(self, etype, **fields):
        ev = {"seq": self._seq, "session_id": self.session_id, "type": etype}
        ev.update(fields)
        self.events.append(ev)
        self._seq += 1
        return self

    def open(self, agent_id="demo-agent"):
        return self.add("session_open", agent_id=agent_id)

    def say(self, uid, text, role="assistant"):
        self.add("utterance_begin", utterance_id=uid, role=role)
        for c in _chunks(text):
            self.add("utterance_chunk", utterance_id=uid, delta=c)
        return self.add("utterance_seal", utterance_id=uid, final_text=text)

    def call(self, iid, tool, args_obj):
        raw = json.dumps(args_obj, sort_keys=True)
        self.add("invocation_begin", invocation_id=iid, tool_name=tool)
        for c in _chunks(raw):
            self.add("invocation_args_chunk", invocation_id=iid, args_delta=c)
        return self.add("invocation_end", invocation_id=iid)

    def close(self, status="completed"):
        return self.add("session_close", status=status)


def clean_text_only():
    b = Builder("clean-text")
    b.open().say("u1", "The report is ready.").close()
    return b.events


def clean_tool_and_state():
    b = Builder("clean-tool-state")
    b.open()
    b.add("state_full", state={"cart": {"count": 1}, "step": "pick"})
    b.add("state_patch", patch=[{"op": "set", "path": "cart.count", "value": 2},
                                {"op": "set", "path": "step", "value": "pay"}])
    b.add("state_full", state={"cart": {"count": 2}, "step": "pay"})
    b.call("i1", "lookup_price", {"sku": "A-1", "qty": 2})
    b.say("u1", "Your total is ready.")
    b.close()
    return b.events


def clean_error_terminal():
    b = Builder("clean-error")
    b.open().say("u1", "Working on it.")
    b.add("session_error", error_code="UPSTREAM_TIMEOUT",
          message="The upstream tool timed out.")
    return b.events


def clean_multi_utterance():
    b = Builder("clean-multi")
    b.open()
    b.say("u1", "First part.", role="assistant")
    b.call("i1", "search_docs", {"query": "refund policy"})
    b.say("u2", "Second part, with the answer.")
    b.close()
    return b.events


def broken_out_of_order():
    b = Builder("broken-out-of-order")
    b.open()
    # Chunk arrives before its begin: lifecycle violation only, because
    # the utterance *is* begun later in the stream.
    b.add("utterance_chunk", utterance_id="u1", delta="Hello ")
    b.add("utterance_begin", utterance_id="u1", role="assistant")
    b.add("utterance_chunk", utterance_id="u1", delta="world.")
    b.add("utterance_seal", utterance_id="u1", final_text="Hello world.")
    b.close()
    return b.events


def broken_missing_terminal():
    b = Builder("broken-missing-terminal")
    b.open().say("u1", "This stream just stops.")
    return b.events


def broken_malformed_payload():
    b = Builder("broken-malformed")
    b.open()
    # invocation_begin without tool_name: schema violation only.
    b.add("invocation_begin", invocation_id="i1")
    b.add("invocation_args_chunk", invocation_id="i1", args_delta="{\"ok\": true}")
    b.add("invocation_end", invocation_id="i1")
    b.say("u1", "Done.")
    b.close()
    return b.events


def broken_delta_mismatch():
    b = Builder("broken-delta-mismatch")
    b.open()
    b.add("utterance_begin", utterance_id="u1", role="assistant")
    b.add("utterance_chunk", utterance_id="u1", delta="The total is ")
    b.add("utterance_chunk", utterance_id="u1", delta="$41.")
    b.add("utterance_seal", utterance_id="u1", final_text="The total is $42.")
    b.close()
    return b.events


def broken_tool_args_json():
    b = Builder("broken-tool-args")
    b.open()
    b.add("invocation_begin", invocation_id="i1", tool_name="lookup_price")
    b.add("invocation_args_chunk", invocation_id="i1", args_delta="{\"city\": \"Dallas\",")
    b.add("invocation_args_chunk", invocation_id="i1", args_delta="}")
    b.add("invocation_end", invocation_id="i1")
    b.close()
    return b.events


def broken_state_patch():
    b = Builder("broken-state-patch")
    b.open()
    b.add("state_full", state={"cart": {"count": 1}})
    b.add("state_patch", patch=[{"op": "set", "path": "cart.count", "value": 2}])
    # Patch says 2, snapshot says 3.
    b.add("state_full", state={"cart": {"count": 3}})
    b.close()
    return b.events


CLEAN = {"clean_text_only": clean_text_only,
         "clean_tool_and_state": clean_tool_and_state,
         "clean_error_terminal": clean_error_terminal,
         "clean_multi_utterance": clean_multi_utterance}

BROKEN = {"broken_out_of_order": (broken_out_of_order, "lifecycle_order"),
          "broken_missing_terminal": (broken_missing_terminal, "terminal_present"),
          "broken_malformed_payload": (broken_malformed_payload, "payload_schema"),
          "broken_delta_mismatch": (broken_delta_mismatch, "text_reassembly"),
          "broken_tool_args_json": (broken_tool_args_json, "tool_args_reassembly"),
          "broken_state_patch": (broken_state_patch, "state_patch_chain")}


def all_sessions():
    out = {}
    for name, fn in CLEAN.items():
        out[name] = fn()
    for name, (fn, _rule) in BROKEN.items():
        out[name] = fn()
    return out
