"""Apply simple state patches. Stdlib only.

A patch is a list of operations:
  {"op": "set", "path": "cart.count", "value": 3}
  {"op": "delete", "path": "cart.coupon"}
Paths are dotted keys into nested dicts. apply_patch never mutates its input.
"""
import copy


class PatchError(ValueError):
    pass


def _parts(path):
    if not isinstance(path, str) or not path:
        raise PatchError("patch path must be a non-empty string")
    parts = path.split(".")
    if any(not p for p in parts):
        raise PatchError("patch path has an empty segment: %r" % path)
    return parts


def apply_patch(state, patch):
    """Return a new state dict with `patch` applied. Raises PatchError."""
    if not isinstance(state, dict):
        raise PatchError("state must be a dict")
    if not isinstance(patch, list):
        raise PatchError("patch must be a list of operations")
    out = copy.deepcopy(state)
    for op in patch:
        if not isinstance(op, dict):
            raise PatchError("patch operation must be a dict")
        kind = op.get("op")
        parts = _parts(op.get("path"))
        if kind == "set":
            if "value" not in op:
                raise PatchError("set operation requires a value")
            node = out
            for part in parts[:-1]:
                nxt = node.get(part)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[part] = nxt
                node = nxt
            node[parts[-1]] = copy.deepcopy(op["value"])
        elif kind == "delete":
            node = out
            for part in parts[:-1]:
                nxt = node.get(part)
                if not isinstance(nxt, dict):
                    raise PatchError("delete path does not exist: %r" % op.get("path"))
                node = nxt
            if parts[-1] not in node:
                raise PatchError("delete path does not exist: %r" % op.get("path"))
            del node[parts[-1]]
        else:
            raise PatchError("unknown patch op: %r" % (kind,))
    return out
