# ADR-0006: Follow LangGraph execution with a LangChain callback handler, never by rewriting the graph

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
The langgraph.py docstring: callbacks fire for `.invoke()`, `.ainvoke()`, `.stream()` and `.astream()` alike, so "the caller does not have to restructure anything to be watched". The README states it "does not rewrite the graph".

## Decision
`attach(graph)` publishes topology and returns a config with a `LoopScopeCallback` appended to any existing callbacks (plus a `_loopscope` escape hatch). Real node executions are identified by a `graph:step:N` tag, because inner runnables inherit `metadata["langgraph_node"]` and would double-count. Node identity is a stable path built from `langgraph_checkpoint_ns`. The handler sets `raise_error = False` ("a broken dashboard must never kill the graph run"), emits node start/end/error with timing, state deltas with changed keys, tool and model logs, and token usage from three provider shapes or from `loopscope` custom events. Edges are emitted in observed execution order.

## Consequences
**Positive**
- No changes to user graphs; works for every invocation style.
- Dashboard failures cannot break a run.

**Negative**
- Handoffs are inferred from execution order, so parallel fan-out is approximate (README says so).
- Depends on LangGraph's tag and metadata conventions, which can change between versions.

## Alternatives considered
- `astream_events`, rejected in the docstring because it would force callers to restructure their invocation.

## Evidence
- loopscope/langgraph.py (`LoopScopeCallback`, `attach`, `finish`, `node_path`, `_token_usage`)
- README.md ("LangGraph", "Under the hood")
- tests/test_nested_graphs.py
- commit 1886c92
