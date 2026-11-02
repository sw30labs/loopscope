# ADR-0014: Keep LangGraph optional so Ralph-only users install a small core

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
Ralph loops need no LangChain. The `attach` docstring: "Imported lazily so LangChain stays optional."

## Decision
Core dependencies are fastapi, uvicorn[standard] and websockets, with Python >=3.10. LangGraph is the `langgraph` extra and pytest, langgraph and httpx are the `dev` extra. `loopscope.attach`/`finish` import the LangGraph module lazily, and that module falls back to a stub `BaseCallbackHandler` if langchain_core is missing. LangGraph tests use `pytest.importorskip`.

## Consequences
**Positive**
- `import loopscope` never requires LangChain.

**Negative**
- LangGraph compatibility is not pinned; behaviour depends on the installed version.

## Alternatives considered
- A hard LangGraph dependency. Not evidenced as considered.

## Evidence
- pyproject.toml
- requirements.txt
- loopscope/__init__.py (`attach`, `finish`)
- loopscope/langgraph.py (import fallback)
- tests/test_nested_graphs.py
