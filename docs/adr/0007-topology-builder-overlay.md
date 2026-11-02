# ADR-0007: Recover full topology by overlaying the StateGraph builder on get_graph() and inferring router targets

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
Compiled `get_graph()` draws a conditional edge without a path_map as `node -> __end__` and drops everything behind that router, so later chains showed up as disconnected nodes. The test docstring names the "STRIDE-Lite shape" as the case that exposed this.

## Decision
`extract_topology` merges nodes and edges from `get_graph()` with the original builder (`compiled.builder`): static edges, waiting edges and branches. When a branch has no path_map, destinations are inferred from a `Literal[...]` return hint, then from string constants and END/START names in the function's bytecode (which works for `exec`'d code), then from its source AST. Only known node ids are accepted. A stub `src -> __end__` from the drawable is dropped when the builder already names real destinations. Start and end terminals are added when missing, and sinks get an edge to `__end__`.

## Consequences
**Positive**
- Graphs draw correctly even without path_maps.
- Covered by synthetic and real-LangGraph tests.

**Negative**
- Inference can over-include a node whose name appears as a string literal in a router but is never returned.
- Reads private-ish LangGraph attributes (`builder`, `branches`, `waiting_edges`).

## Alternatives considered
- Trusting `get_graph()` alone, which is what produced the broken drawings.

## Evidence
- loopscope/langgraph.py (`extract_topology`, `_from_builder`, `_infer_destinations`, `_merge_topology`, `_ensure_terminals`)
- tests/test_langgraph_helpers.py (`test_truncated_drawable_recovers_second_chain`, `test_infers_router_from_bytecode_when_source_is_gone`, `test_real_langgraph_stride_and_scenario_shapes`)
- commit 1886c92
