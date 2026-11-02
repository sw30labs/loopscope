# ADR-0015: Test Python with pytest and the dashboard script with a dependency-free Node harness

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
Most of the dashboard's correctness is event handling in JavaScript. The test docstring: the harness "executes the actual dashboard script with a small DOM. Visual appearance is intentionally left to browser QA."

## Decision
Python behaviour is covered by pytest (events, bus, Ralph, replay and origin checks, layout, LangGraph helpers, nested graphs). `tests/dashboard_activity.cjs` extracts the inline script from dashboard.html, runs it in a `node:vm` context with a mock DOM, clock and WebSocket, and exposes its closure for 15 named scenarios driven by `test_dashboard_activity.py`. Tests skip when Node or LangGraph is missing. There is no CI workflow; `setup_and_run.sh` runs the suite before demos.

## Consequences
**Positive**
- Real shipped script under test, with no npm dependencies.

**Negative**
- Layout, CSS and accessibility are not automated.
- Without CI, tests only run when someone runs them (A-006).

## Alternatives considered
- jsdom or a headless browser. Not evidenced as considered; the harness avoids npm deps by design.

## Evidence
- tests/
- tests/dashboard_activity.cjs
- tests/test_dashboard_activity.py
- setup_and_run.sh
- commits a38579e, 90ecae3, 0e2d8fa
