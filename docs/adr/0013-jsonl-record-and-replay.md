# ADR-0013: Optional JSONL recording and a replay CLI for post-mortems

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
The replay.py docstring: "Overnight Ralph loops finish while you are asleep. This plays the tape back at whatever speed you can stand."

## Decision
`start(jsonl=path)` or `EventBus(jsonl_path=...)` appends every event as one JSON line from a background writer thread, so publishing never waits on disk. The file is created with mode 0600. A bus can record to only one path; attaching the same path again is a no-op and a different path raises. `loopscope-replay` (`python -m loopscope.replay`) skips torn lines and replay frames, starts a dashboard, and republishes events with the original gaps scaled by `--speed` (default 4) and capped by `--max-gap` (default 2 s).

## Consequences
**Positive**
- A full tape that survives the ring buffer.
- Post-mortems look like the live view.

**Negative**
- The writer opens the file per line and swallows errors, so a disk problem loses events silently.
- Replay re-stamps timestamps to now.

## Alternatives considered
- None evidenced.

## Evidence
- loopscope/bus.py (`set_jsonl`, `_jsonl_writer`)
- loopscope/replay.py
- pyproject.toml (`loopscope-replay` script)
- tests/test_bus.py (jsonl tests)
- tests/test_replay_and_server.py (`test_load_events_skips_torn_and_replay`)
