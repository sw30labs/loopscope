# ADR-0005: Bind to loopback with no authentication, plus a WebSocket origin check

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
The dashboard shows agent state, which can include prompts and outputs. The README's Security section says it binds to 127.0.0.1, has no authentication, and should not be exposed without an authenticated tunnel or proxy.

## Decision
Default host is 127.0.0.1. The WebSocket accepts a browser only when `Origin` equals `http(s)://<Host header>`, or a client with no Origin only from 127.0.0.1/::1/localhost; anything else is closed with code 1008. Binding to 0.0.0.0 or :: prints a "no auth, reachable from the network" warning. FastAPI's docs, redoc and OpenAPI routes are disabled. Ports outside 1-65535 are rejected.

## Consequences
**Positive**
- Safe by default for a single developer's machine.
- Cross-site pages cannot open the WebSocket from a different origin.

**Negative**
- No auth at all once someone can reach the port.
- The origin check compares Origin with the request's own Host header, and there is no Host allow-list, so it does not by itself stop a DNS-rebinding page; `/api/replay` has no origin check. This is recorded here as an observation, not changed (A-003).

## Alternatives considered
- Token auth or TLS. Not evidenced as considered; the README defers to an external authenticated tunnel or proxy.

## Evidence
- loopscope/server.py (`_origin_allowed`, `create_app`, `Dashboard.start`, `start`)
- README.md ("Security")
- tests/test_replay_and_server.py (origin tests)
- commit 1886c92
