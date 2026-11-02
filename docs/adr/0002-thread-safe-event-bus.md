# ADR-0002: One in-process EventBus with fire-and-forget publish, ring buffer and pinned topology

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
Producers run on arbitrary threads (sync `.invoke()` on the main thread, async apps on their own loop, worker pools), while the dashboard runs on its own event loop (ADR-0004). The bus docstring says `publish()` "has to be callable from anywhere and must never block or raise into the caller's hot path". A browser that connects late still needs recent history and the graph to draw.

## Decision
`EventBus` stamps a monotonic `seq` under a lock, appends to a `deque(maxlen=4000)` and keeps the latest `graph.topology` per run outside the ring so it is never evicted. Fan-out to subscribers is scheduled with `loop.call_soon_threadsafe`; a full subscriber queue (maxsize 1000) drops its oldest event instead of blocking the producer. `subscribe_and_replay()` registers a subscriber and snapshots under the same lock, and the WebSocket sender skips live events with `seq <= last_seq` so nothing is duplicated or lost at connect time. A module-level default bus lets `start()`, `RalphLoop` and `attach()` share one bus without passing it around.

## Consequences
**Positive**
- Instrumentation can never stall or crash the agent run.
- Late browsers get topology plus recent events; the connect race is covered by a test.

**Negative**
- Long overnight loops wrap the 4000-event buffer and lose early events unless JSONL is on (stated in the README).
- Slow browsers silently drop events.
- The module-level default bus is global state.

## Alternatives considered
- Unbounded history, or a blocking queue. Not evidenced as considered; the sizes 4000 and 1000 have no recorded rationale (A-002).

## Evidence
- loopscope/bus.py
- loopscope/server.py (`stream`)
- tests/test_bus.py (`test_subscribe_and_replay_skips_in_flight_duplicates`, `test_publish_drops_replay_type`)
- README.md ("Under the hood")
- commit 1886c92
