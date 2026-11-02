# Architecture Decision Records

Retrospective ADRs for loopscope, written on 2026-11-02 from a full read of the repository at `423e245` (main). Each one records a decision the code, docs and history show was made. Where the reason isn't stated in the repo it is marked as inferred and logged in [../assumptions.md](../assumptions.md).

Format: Title, Status, Context, Decision, Consequences (positive and negative), Alternatives considered, Evidence.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-local-in-process-dashboard.md) | Run loopscope as an in-process local dashboard, not a hosted service | Accepted (retrospective, inferred 2026-11-02) |
| [0002](0002-thread-safe-event-bus.md) | One in-process EventBus with fire-and-forget publish, ring buffer and pinned topology | Accepted (retrospective, inferred 2026-11-02) |
| [0003](0003-flat-event-envelope.md) | A flat event envelope with a fixed string vocabulary | Accepted (retrospective, inferred 2026-11-02) |
| [0004](0004-server-on-own-thread.md) | Run the dashboard server on its own daemon thread and event loop | Accepted (retrospective, inferred 2026-11-02) |
| [0005](0005-loopback-no-auth.md) | Bind to loopback with no authentication, plus a WebSocket origin check | Accepted (retrospective, inferred 2026-11-02) |
| [0006](0006-langgraph-callback-handler.md) | Follow LangGraph execution with a LangChain callback handler, never by rewriting the graph | Accepted (retrospective, inferred 2026-11-02) |
| [0007](0007-topology-builder-overlay.md) | Recover full topology by overlaying the StateGraph builder on get_graph() and inferring router targets | Accepted (retrospective, inferred 2026-11-02) |
| [0008](0008-nested-subgraphs-one-run.md) | Show nested subgraphs as namespaced work nodes on the parent run | Accepted (retrospective, inferred 2026-11-02) |
| [0009](0009-ralph-loop-iterator.md) | Model a Ralph loop as an iterator with a convergence signal, stall detection and flag-based termination | Accepted (retrospective, inferred 2026-11-02) |
| [0010](0010-server-side-layout.md) | Compute graph layout in Python and keep the browser a renderer | Accepted (retrospective, inferred 2026-11-02) |
| [0011](0011-single-file-vanilla-dashboard.md) | Ship the UI as one self-contained HTML file with vanilla JS and SVG | Accepted (retrospective, inferred 2026-11-02) |
| [0012](0012-truncate-and-redact-state.md) | Truncate state and redact secret-shaped keys before anything leaves the process | Accepted (retrospective, inferred 2026-11-02) |
| [0013](0013-jsonl-record-and-replay.md) | Optional JSONL recording and a replay CLI for post-mortems | Accepted (retrospective, inferred 2026-11-02) |
| [0014](0014-optional-langgraph-dependency.md) | Keep LangGraph optional so Ralph-only users install a small core | Accepted (retrospective, inferred 2026-11-02) |
| [0015](0015-tests-pytest-and-node-harness.md) | Test Python with pytest and the dashboard script with a dependency-free Node harness | Accepted (retrospective, inferred 2026-11-02) |
| [0016](0016-beta-packaging-and-launcher.md) | Release as an Apache-2.0 0.1 beta with a one-script setup and demo launcher | Accepted (retrospective, inferred 2026-11-02) |
| [0017](0017-ship-agent-integration-skill.md) | Ship an agent skill that wires loopscope into other projects | Accepted (retrospective, inferred 2026-11-02) |
