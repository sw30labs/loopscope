# ADR-0001: Run loopscope as an in-process local dashboard, not a hosted service

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
Agent runs (LangGraph graphs and Ralph loops) are usually scripts on the developer's machine. The README positions loopscope as a "local dashboard" that "runs inside your Python process" with "no collector, no database, and no account", and the package docstring shows a three-line integration (`start`, `attach`, `RalphLoop`).

## Decision
loopscope is a pip-installable library imported into the agent's own process. `loopscope.start()` brings up a FastAPI/uvicorn server on 127.0.0.1:7788 serving one HTML page, a `/api/replay` JSON endpoint, `/healthz` and a `/ws` WebSocket. There is no external collector, persistence layer or account system; history lives in memory unless JSONL recording is turned on (ADR-0013).

## Consequences
**Positive**
- Zero infrastructure: install, add a few lines, open a browser.
- Nothing leaves the machine by default.

**Negative**
- The dashboard lives and dies with the process; `Dashboard.hold()` exists so a finished script keeps the page up.
- No multi-run history, search or team sharing; one process, one bus.

## Alternatives considered
- A hosted tracing service or OpenTelemetry collector (LangSmith-style). Not evidenced as considered; the README contrasts itself only implicitly ("no collector, no database, and no account"). See A-001.

## Evidence
- README.md ("What it is")
- loopscope/__init__.py
- loopscope/server.py (`create_app`, `start`)
- pyproject.toml (deps: fastapi, uvicorn[standard], websockets)
- commit 1886c92
