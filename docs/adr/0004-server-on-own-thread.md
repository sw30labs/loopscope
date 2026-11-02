# ADR-0004: Run the dashboard server on its own daemon thread and event loop

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
Users call `loopscope.start()` from ordinary scripts and expect it to return immediately. The server.py docstring: it "Runs on its own thread with its own event loop so that `start()` returns immediately and your script keeps its main thread."

## Decision
`Dashboard.start()` builds a `uvicorn.Server` and runs it on a daemon thread named `loopscope`, waits up to 5 s for `server.started`, and raises `RuntimeError("loopscope could not bind ...")` if the thread dies first. The FastAPI lifespan hook binds the bus to the server's running loop. `hold()` blocks until Ctrl-C; `stop()` sets `should_exit` and joins.

## Consequences
**Positive**
- Works with sync and async callers alike.
- Bind failures surface at `start()` rather than as a silent dead page.

**Negative**
- The daemon thread dies with the process, so short scripts need `hold()`.
- Every producer crosses a thread boundary, which is why the bus must be thread-safe (ADR-0002).

## Alternatives considered
- Running inside the caller's own asyncio loop. Not evidenced as considered.

## Evidence
- loopscope/server.py (`Dashboard`, `_wait_until_up`)
- tests/test_replay_and_server.py (`test_wait_until_up_dead_thread`)
- commit 1886c92
