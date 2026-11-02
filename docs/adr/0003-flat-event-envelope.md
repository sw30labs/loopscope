# ADR-0003: A flat event envelope with a fixed string vocabulary

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
The same events go over the WebSocket, into an optional JSONL file and back through the replay CLI. The events.py docstring: "One flat envelope so the websocket payload stays trivial to parse on the client and trivial to persist to a JSONL file for replay later."

## Decision
Every event is `{...payload, type, run_id, ts, seq}` with the envelope keys written last, so a payload cannot overwrite them. Types are plain strings the dashboard switches on: `run.start/end`, `graph.topology`, `node.start/end/error`, `edge.traverse`, `iter.start/end`, `state.delta`, `log`, `metric`. `replay` is reserved for the client-side snapshot frame; `publish()` and the replay loader both drop it.

## Consequences
**Positive**
- One format for live, recorded and replayed data.
- The client needs no schema library.

**Negative**
- No version field in the envelope; format changes have to stay backward compatible (the dashboard already carries code to compact older marker-heavy topologies).

## Alternatives considered
- None evidenced.

## Evidence
- loopscope/events.py
- loopscope/replay.py (`load_events`)
- tests/test_events.py (`test_as_dict_envelope_wins`)
- tests/test_replay_and_server.py
- commit 1886c92
