import json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_event_contract.streams import Builder, all_sessions, BROKEN, CLEAN
from ui_event_contract.validator import RULES, validate_session

SESSIONS = all_sessions()

def rep(name):
    return validate_session(SESSIONS[name])

class TestClean(unittest.TestCase):
    def test_clean_text_only(self): self.assertTrue(rep("clean_text_only").passed)
    def test_clean_tool_and_state(self): self.assertTrue(rep("clean_tool_and_state").passed)
    def test_clean_error_terminal(self): self.assertTrue(rep("clean_error_terminal").passed)
    def test_clean_multi(self): self.assertTrue(rep("clean_multi_utterance").passed)
    def test_all_rules_present(self):
        self.assertEqual(set(rep("clean_text_only").rules), set(RULES))
    def test_no_weighted_score(self):
        d = rep("clean_text_only").to_dict()
        self.assertNotIn("score", d); self.assertIn("passed", d)

class TestBrokenIsolation(unittest.TestCase):
    def _check(self, name, rule):
        r = rep(name)
        self.assertFalse(r.passed)
        failed = [k for k, v in r.rules.items() if not v.passed]
        self.assertEqual(failed, [rule], "%s failed %s" % (name, failed))
    def test_out_of_order(self): self._check("broken_out_of_order", "lifecycle_order")
    def test_missing_terminal(self): self._check("broken_missing_terminal", "terminal_present")
    def test_malformed(self): self._check("broken_malformed_payload", "payload_schema")
    def test_delta_mismatch(self): self._check("broken_delta_mismatch", "text_reassembly")
    def test_tool_args(self): self._check("broken_tool_args_json", "tool_args_reassembly")
    def test_state_patch(self): self._check("broken_state_patch", "state_patch_chain")

class TestLifecycle(unittest.TestCase):
    def test_empty_stream(self):
        r = validate_session([]); self.assertFalse(r.passed)
        self.assertFalse(r.rules["lifecycle_order"].passed)
        self.assertFalse(r.rules["terminal_present"].passed)
    def test_first_must_be_open(self):
        b = Builder("x"); b.say("u1", "hi."); b.close()
        self.assertFalse(validate_session(b.events).rules["lifecycle_order"].passed)
    def test_event_after_terminal(self):
        b = Builder("x"); b.open().close(); b.say("u1", "late.")
        r = validate_session(b.events)
        self.assertFalse(r.rules["lifecycle_order"].passed)
    def test_non_increasing_seq(self):
        evs = Builder("x").open().say("u1", "hi.").close().events
        evs[1]["seq"] = 0
        self.assertFalse(validate_session(evs).rules["lifecycle_order"].passed)
    def test_chunk_after_seal(self):
        b = Builder("x"); b.open(); b.say("u1", "hi.")
        b.add("utterance_chunk", utterance_id="u1", delta="!")
        b.close()
        self.assertFalse(validate_session(b.events).rules["lifecycle_order"].passed)
    def test_two_terminals_fail_terminal_rule(self):
        b = Builder("x"); b.open().close()
        b.add("session_error", error_code="E", message="m")
        self.assertFalse(validate_session(b.events).rules["terminal_present"].passed)
    def test_error_is_terminal(self):
        self.assertTrue(rep("clean_error_terminal").rules["terminal_present"].passed)

class TestSchema(unittest.TestCase):
    def test_unknown_type(self):
        b = Builder("x"); b.open(); b.add("mystery_event"); b.close()
        self.assertFalse(validate_session(b.events).rules["payload_schema"].passed)
    def test_bad_role(self):
        b = Builder("x"); b.open(); b.say("u1", "hi.", role="narrator"); b.close()
        self.assertFalse(validate_session(b.events).rules["payload_schema"].passed)
    def test_bad_close_status(self):
        b = Builder("x"); b.open(); b.close(status="done-ish")
        self.assertFalse(validate_session(b.events).rules["payload_schema"].passed)
    def test_delta_wrong_type(self):
        b = Builder("x"); b.open()
        b.add("utterance_begin", utterance_id="u1", role="assistant")
        b.add("utterance_chunk", utterance_id="u1", delta=42)
        b.add("utterance_seal", utterance_id="u1", final_text="")
        b.close()
        self.assertFalse(validate_session(b.events).rules["payload_schema"].passed)
    def test_missing_seq(self):
        evs = Builder("x").open().close().events; del evs[0]["seq"]
        self.assertFalse(validate_session(evs).rules["payload_schema"].passed)

class TestReferenceIntegrity(unittest.TestCase):
    def test_duplicate_seq(self):
        evs = Builder("x").open().say("u1", "hi.").close().events
        evs[-1]["seq"] = evs[-2]["seq"]
        r = validate_session(evs)
        self.assertFalse(r.rules["reference_integrity"].passed)
    def test_orphan_reference(self):
        b = Builder("x"); b.open()
        b.add("utterance_chunk", utterance_id="ghost", delta="boo")
        b.close()
        r = validate_session(b.events)
        self.assertFalse(r.rules["reference_integrity"].passed)
    def test_duplicate_begin(self):
        b = Builder("x"); b.open(); b.say("u1", "hi.")
        b.add("utterance_begin", utterance_id="u1", role="assistant"); b.close()
        self.assertFalse(validate_session(b.events).rules["reference_integrity"].passed)

class TestReassembly(unittest.TestCase):
    def test_text_exact_match_passes(self):
        self.assertTrue(rep("clean_multi_utterance").rules["text_reassembly"].passed)
    def test_tool_args_valid_json_passes(self):
        self.assertTrue(rep("clean_tool_and_state").rules["tool_args_reassembly"].passed)
    def test_tool_args_scalar_json_parses(self):
        b = Builder("x"); b.open()
        b.add("invocation_begin", invocation_id="i1", tool_name="t")
        b.add("invocation_args_chunk", invocation_id="i1", args_delta="[1, 2]")
        b.add("invocation_end", invocation_id="i1"); b.close()
        self.assertTrue(validate_session(b.events).rules["tool_args_reassembly"].passed)
    def test_no_invocation_is_vacuous_pass(self):
        self.assertTrue(rep("clean_text_only").rules["tool_args_reassembly"].passed)
    def test_no_state_is_vacuous_pass(self):
        self.assertTrue(rep("clean_text_only").rules["state_patch_chain"].passed)
    def test_unsealed_utterance_not_checked_for_text(self):
        b = Builder("x"); b.open()
        b.add("utterance_begin", utterance_id="u1", role="assistant")
        b.add("utterance_chunk", utterance_id="u1", delta="draft")
        b.close()
        self.assertTrue(validate_session(b.events).rules["text_reassembly"].passed)

if __name__ == "__main__":
    unittest.main()
