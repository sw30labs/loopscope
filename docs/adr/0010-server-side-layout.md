# ADR-0010: Compute graph layout in Python and keep the browser a renderer

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
The layout.py docstring: agent graphs are cyclic, so a plain topological sort is not enough, and "Doing this in Python rather than in the browser keeps the client dumb: it receives coordinates and renders them."

## Decision
`topology.pack()` is shared by both hooks so LangGraph and Ralph produce identical payloads. It finds back-edges with an iterative DFS, layers the rest by longest path, orders layers with two barycenter sweeps, and also computes a radial constellation in which a node becomes the hub only if its degree is above 2 and strictly higher than every other node's. `choose_pane` picks constellation for a hub or a terminal-less cycle and flowchart for a pipeline with start/end. Colours come from a fixed palette with red reserved for the hub, and stages for the stepper come from the layers.

## Consequences
**Positive**
- No JavaScript graph library; deterministic layout that is tested in Python.
- Ralph cycles and supervisors read naturally.

**Negative**
- Layout is recomputed and resent with each topology publish.
- The browser still has to re-pack positions when it hides markers (ADR-0008).

## Alternatives considered
- Browser-side layout (e.g. a JS graph library). Rejected implicitly by the docstring's "keeps the client dumb".

## Evidence
- loopscope/layout.py
- loopscope/topology.py
- tests/test_layout.py
- commits 1886c92, 90ecae3
