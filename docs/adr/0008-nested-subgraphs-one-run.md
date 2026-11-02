# ADR-0008: Show nested subgraphs as namespaced work nodes on the parent run

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
Graphs that invoke other graphs used to either open a separate run that took over the parent's view, or count a wrapper node as well as its children. Commit 8e77550 kept nested jobs from stealing the parent mesh; commits 90ecae3 and 0e2d8fa (PR #1, branch `codex/album-stategraphs`) exposed nested stages and showed only work nodes.

## Decision
Subgraphs that are compiled nodes are expanded automatically into `parent/child` ids with entry and exit markers. Graphs called from inside a node function are declared with `compiled.loopscope_subgraphs = {...}` or discovered at runtime with `config["_loopscope"].include_subgraph(child, metadata)`, which republishes topology on the same run. Container nodes and markers are excluded from counts and timings; transitions walk through markers so emitted edges exist in the expanded topology. Recursion is guarded by object identity. In the browser, a topology or run event from another run_id while the current run is live is treated as foreign and does not replace the mesh, and marker nodes are hidden with edges joined across them, while the raw event is kept for replay. `capture_errors=False` keeps exception text out of events.

## Consequences
**Positive**
- One timeline for multi-level graphs, with no double counting.
- Parallel discovered subgraphs keep both branches (tested).

**Negative**
- More complex handler state (containers, terminal ids, edge targets) behind locks.
- Dynamic discovery requires a line of user code in the wrapper.

## Alternatives considered
- A separate `attach()` per subgraph, which the README now advises against because it creates a separate run.

## Evidence
- loopscope/langgraph.py (`extract_topology`, `include_subgraph`, `_transition`, `on_custom_event`)
- loopscope/static/dashboard.html (`liveForeign`, `compactTopology`, `onEdge`)
- tests/test_nested_graphs.py
- tests/dashboard_activity.cjs (nested, compact_nodes, marker_* scenarios)
- README.md ("Nested graphs")
- commits 8e77550, 90ecae3, 0e2d8fa, 423e245
