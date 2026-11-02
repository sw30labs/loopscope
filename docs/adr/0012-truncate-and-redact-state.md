# ADR-0012: Truncate state and redact secret-shaped keys before anything leaves the process

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
Agent state grows fast and can hold credentials. The events.py comment: "nobody reads a 40 KB dict in a log pane. Keep shape, drop bulk." The tests describe the dashboard as "a watch UI, not an audit".

## Decision
`truncate`/`summarize_state` keep at most 40 keys, 12 list items and 600 characters (halved at each nesting level), shorten keys over 64 characters, and replace values whose key matches password, secret, token, api key, authorization, bearer or cookie with a dash. Pydantic models, dataclass-like objects and `Command.update` are unwrapped. Log text is capped at 800 characters and errors at 400. `attach(..., capture_state=False)` stops state deltas and `capture_errors=False` keeps only the exception type.

## Consequences
**Positive**
- Bounded payloads, and common secret keys don't reach the browser or JSONL.
- Opt-outs for sensitive runs.

**Negative**
- Redaction is by key name only; a secret inside a message string or under an innocuous key passes through (A-004).
- The dashboard is deliberately not a faithful audit record.

## Alternatives considered
- Full state capture. Not evidenced as considered.

## Evidence
- loopscope/events.py (`truncate`, `summarize_state`, `_SECRET_KEY`)
- loopscope/langgraph.py (`capture_state`, `capture_errors`)
- tests/test_events.py
- tests/test_nested_graphs.py (`test_exception_bodies_can_be_omitted_without_changing_failure`)
- README.md ("Security")
