import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_event_contract.statepatch import PatchError, apply_patch

class TestPatch(unittest.TestCase):
    def test_set_top(self):
        self.assertEqual(apply_patch({"a": 1}, [{"op": "set", "path": "b", "value": 2}]),
                         {"a": 1, "b": 2})
    def test_set_nested_creates(self):
        self.assertEqual(apply_patch({}, [{"op": "set", "path": "a.b.c", "value": 1}]),
                         {"a": {"b": {"c": 1}}})
    def test_delete(self):
        self.assertEqual(apply_patch({"a": {"b": 1, "c": 2}},
                                     [{"op": "delete", "path": "a.b"}]), {"a": {"c": 2}})
    def test_delete_missing_raises(self):
        with self.assertRaises(PatchError):
            apply_patch({"a": 1}, [{"op": "delete", "path": "zz"}])
    def test_unknown_op_raises(self):
        with self.assertRaises(PatchError):
            apply_patch({}, [{"op": "move", "path": "a"}])
    def test_set_requires_value(self):
        with self.assertRaises(PatchError):
            apply_patch({}, [{"op": "set", "path": "a"}])
    def test_input_not_mutated(self):
        src = {"a": {"b": 1}}
        apply_patch(src, [{"op": "set", "path": "a.b", "value": 9}])
        self.assertEqual(src, {"a": {"b": 1}})
    def test_empty_path_raises(self):
        with self.assertRaises(PatchError):
            apply_patch({}, [{"op": "set", "path": "", "value": 1}])
    def test_patch_not_list_raises(self):
        with self.assertRaises(PatchError):
            apply_patch({}, {"op": "set"})
    def test_multi_op_order(self):
        out = apply_patch({"n": 1}, [{"op": "set", "path": "n", "value": 2},
                                     {"op": "set", "path": "n", "value": 3}])
        self.assertEqual(out["n"], 3)

if __name__ == "__main__":
    unittest.main()
