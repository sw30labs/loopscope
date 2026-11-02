# ADR-0016: Release as an Apache-2.0 0.1 beta with a one-script setup and demo launcher

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
The first commit is titled "loopscope 0.1 Beta" and is tagged `v0.1.0-beta`.

## Decision
Version 0.1.0b1 under Apache-2.0 (copyright Nicolas Cravino), installed from source with `pip install -e`. `setup_and_run.sh` picks the newest Python >=3.10, builds a venv, installs extras, runs tests, and runs the Ralph, LangGraph or Ralph-driving-LangGraph demos. It stops stale loopscope demo processes on the port and refuses to touch a port held by anything else, and works around a macOS 3.13 `.pth` issue with PYTHONPATH. The demos use sleeps instead of models, so no API keys are needed.

## Consequences
**Positive**
- One command from clone to a live demo, with no keys.

**Negative**
- Not published to PyPI (no evidence of a publish workflow); install is from source (A-007).

## Alternatives considered
- None evidenced.

## Evidence
- pyproject.toml
- LICENSE
- setup_and_run.sh
- examples/
- tag v0.1.0-beta -> 1886c92
- commits 1886c92, 22ba634
