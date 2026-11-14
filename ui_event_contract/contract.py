"""The lifecycle contract: event names, payload schemas, terminal types.

Event names are original to this kit. The AG-UI protocol was the
inspiration for the problem (a streamed agent run rendered by a frontend),
not a source copied event-for-event.
"""

# type -> {field: (python types, required)}
SCHEMAS = {
    "session_open": {"agent_id": (str, True), "session_id": (str, True)},
    "utterance_begin": {"session_id": (str, True), "utterance_id": (str, True),
                        "role": (str, True)},
    "utterance_chunk": {"session_id": (str, True), "utterance_id": (str, True),
                        "delta": (str, True)},
    "utterance_seal": {"session_id": (str, True), "utterance_id": (str, True),
                       "final_text": (str, True)},
    "invocation_begin": {"session_id": (str, True), "invocation_id": (str, True),
                         "tool_name": (str, True)},
    "invocation_args_chunk": {"session_id": (str, True),
                              "invocation_id": (str, True),
                              "args_delta": (str, True)},
    "invocation_end": {"session_id": (str, True), "invocation_id": (str, True)},
    "state_full": {"session_id": (str, True), "state": (dict, True)},
    "state_patch": {"session_id": (str, True), "patch": (list, True)},
    "session_close": {"session_id": (str, True), "status": (str, True)},
    "session_error": {"session_id": (str, True), "error_code": (str, True),
                      "message": (str, True)},
}

EVENT_TYPES = tuple(sorted(SCHEMAS))
TERMINAL_TYPES = ("session_close", "session_error")
ROLES = ("assistant", "system", "user")
CLOSE_STATUSES = ("cancelled", "completed", "failed")


def schema_violations(event):
    """Return a list of payload-schema violation strings for one event."""
    if not isinstance(event, dict):
        return ["event is not an object"]
    etype = event.get("type")
    out = []
    if not isinstance(etype, str) or etype not in SCHEMAS:
        return ["unknown or missing event type: %r" % (etype,)]
    seq = event.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        out.append("seq must be a non-negative int")
    for fname, (ftype, required) in SCHEMAS[etype].items():
        if fname not in event:
            if required:
                out.append("%s missing required field %r" % (etype, fname))
            continue
        val = event[fname]
        if not isinstance(val, ftype) or (ftype is str and val == ""):
            out.append("%s field %r must be a non-empty %s"
                       % (etype, fname, ftype.__name__))
    if etype == "utterance_begin" and event.get("role") not in ROLES:
        out.append("utterance_begin role must be one of %s" % (list(ROLES),))
    if etype == "session_close" and "status" in event \
            and event.get("status") not in CLOSE_STATUSES:
        out.append("session_close status must be one of %s" % (list(CLOSE_STATUSES),))
    if etype == "state_patch" and isinstance(event.get("patch"), list):
        for op in event["patch"]:
            if not isinstance(op, dict) or op.get("op") not in ("delete", "set") \
                    or not isinstance(op.get("path"), str):
                out.append("state_patch operations need op in {set, delete} and a string path")
                break
    return out
