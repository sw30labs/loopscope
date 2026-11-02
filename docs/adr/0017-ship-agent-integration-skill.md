# ADR-0017: Ship an agent skill that wires loopscope into other projects

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
The repo includes `skills/loopscope-hook/SKILL.md` and a QUICKSTART-INTEGRATION.md, and the README shows a `/loopscope-hook` screenshot, so integration is meant to be done by coding agents as well as people.

## Decision
The skill tells an agent how to locate the loopscope checkout (`LOOPSCOPE_HOME`, else a default path), install it editable, find the LangGraph `compile()` or loop entry point, and add the minimal `start`/`attach`/`RalphLoop` lines, without hooking tests.

## Consequences
**Positive**
- Repeatable integration across projects.

**Negative**
- The fallback checkout path assumes the author's directory layout (A-008).

## Alternatives considered
- None evidenced.

## Evidence
- skills/loopscope-hook/SKILL.md
- QUICKSTART-INTEGRATION.md
- docs/preview-loopscope-hook.png
- commit 1886c92
