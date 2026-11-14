# agent-ui-event-contract-kit

**Hiring signal:** I can debug the seam where an agent meets its frontend — the streamed event contract — not just the agent itself. When a customer's UI shows a garbled message, a tool call that never fires, or state that drifts from what the agent sent, this kit is how you find which rule the stream broke.

A recorded agent run is a stream of events: a session opens, text arrives in chunks, a tool call's arguments arrive in chunks, shared state is snapshotted and patched, and the session closes. Frontends render that stream live, so a single out-of-order, truncated, or inconsistent event corrupts what the user sees — and ordinary trace/span tools don't check the *streaming* invariants. This kit does.

> **Inspiration, not a copy:** the AG-UI protocol motivated the problem space. The event names here (`session_open`, `utterance_chunk`, `invocation_args_chunk`, `state_patch`, …) are original to this kit and do not copy AG-UI's event names one-for-one.

## The contract — pass/fail per rule, no weighted score

There is deliberately **no conformance score**. Each session gets a pass/fail per rule, plus a count of sessions that pass:

| # | Rule | What it checks |
|---|------|----------------|
| 1 | `lifecycle_order` | `session_open` first, `seq` strictly increasing, text chunks only inside their begin→seal window, tool-arg chunks only inside begin→end, nothing after a terminal event |
| 2 | `terminal_present` | The stream ends with exactly one terminal event (`session_close` or `session_error`) |
| 3 | `payload_schema` | Every event matches the per-type payload schema in `ui_event_contract/contract.py` (required fields, types, role/status vocabularies) |
| 4 | `reference_integrity` | The one generic rule: no duplicate `seq`, no duplicate begin for an id, no chunk/seal/end referencing an id that is never begun |
| 5 | `text_reassembly` | **Stitch the text chunks back together and check they equal the sealed `final_text`** |
| 6 | `tool_args_reassembly` | **Rebuild streamed tool-call arguments from their chunks and check they parse as valid JSON** |
| 7 | `state_patch_chain` | **Apply each `state_patch` to the previous `state_full` snapshot and check it produces the next snapshot** |

Rules 5–7 are the differentiators: they validate what the stream *reconstructs to*, not just the order events arrived in.

State patches are a small original model: a list of `{"op": "set"|"delete", "path": "dotted.key", "value": …}` operations (`ui_event_contract/statepatch.py`, never mutates its input).

## Quick start

```bash
python -m ui_event_contract check fixtures/streams          # per-rule report; exit 0 iff every session passes
python -m ui_event_contract check fixtures/streams/clean-text-only.jsonl
python demo.py                                              # end-to-end demo, exit 0
python evals/run_evals.py                                   # writes evals/eval_report.json
python -m unittest discover -s tests -v
```

Streams are JSONL: one event object per line, in recorded order. `check` on the full planted corpus exits 1 by design — 4 clean sessions pass, 6 broken sessions each fail their planted rule.

## Server

```bash
python -m ui_event_contract serve --host 127.0.0.1 --port 8765
```

`POST /validate` accepts `{"events": [ …one session… ]}` and returns the per-rule report as JSON. `GET /health` returns `{"status": "ok"}`. Binds to `127.0.0.1` by default.

## Planted corpus (`fixtures/streams/`)

Clean (all must pass every rule): `clean-text-only`, `clean-tool-and-state`, `clean-error-terminal`, `clean-multi-utterance`.

One per defect class, each failing **exactly** its planted rule (isolation is asserted by the evals, not just detection):

| Stream | Planted defect | Failing rule |
|--------|----------------|--------------|
| `broken-out-of-order` | text chunk arrives before its begin | `lifecycle_order` |
| `broken-missing-terminal` | stream just stops, no terminal event | `terminal_present` |
| `broken-malformed-payload` | `invocation_begin` missing `tool_name` | `payload_schema` |
| `broken-delta-mismatch` | chunks stitch to “$41.”, seal says “$42.” | `text_reassembly` |
| `broken-tool-args-json` | arg chunks reassemble to `{"city": "Dallas",}` | `tool_args_reassembly` |
| `broken-state-patch` | patch sets `cart.count` to 2, next snapshot says 3 | `state_patch_chain` |

Streams are generated deterministically by `ui_event_contract/streams.py` (fixed chunk-size cycle, no randomness, no network); the committed `.jsonl` files are its output. All data is fictional. Python stdlib only.

## Honest limits

- This validates a *recorded* stream offline; it does not intercept a live stream, and it cannot tell you whether the final text was *true* — only that it matches what was streamed.
- Reassembly rules are vacuous when the corresponding feature is absent (no sealed utterance → `text_reassembly` passes; no snapshots → `state_patch_chain` passes). That is stated, not hidden: absence is a lifecycle/coverage question, not a reassembly failure.
- The patch model covers `set`/`delete` on dotted dict paths only — no list indices, moves, or JSON-Patch semantics.
- Payload schemas are the fixed table in `contract.py`; a vendor extension field is ignored, and an unknown event *type* fails `payload_schema` by design.

## Dev-loop honesty note

No runtime bug was hit while building this kit: the demo, tests, and evals passed on their first full runs, so there is no bug-fix story to tell and none is invented here. The one real design tension, resolved before the tests were finalised: a chunk that arrives *before* its begin could plausibly fail both `lifecycle_order` and `reference_integrity`. The contract separates them on purpose — reference integrity means “never begun anywhere in the stream”, lifecycle means “not yet begun at that point” — so each planted defect fails exactly one rule, and the evals assert that isolation.

## License

MIT — see `LICENSE`. Copyright Akash Bhargava.
