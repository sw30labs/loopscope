# ADR-0011: Ship the UI as one self-contained HTML file with vanilla JS and SVG

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
The dashboard has to install with the Python package and work offline on loopback. pyproject ships only `static/*.html` as package data.

## Decision
`loopscope/static/dashboard.html` holds all CSS and JavaScript inline, with no build step, framework or CDN. It reconnects with backoff, applies a replay snapshot then live events with seq de-duplication, batches painting with `requestAnimationFrame`, and renders the activity bar, stepper, mesh (pan, zoom, fit, focus), pipeline, queue, node status, throughput or pass tape, and live feed. Text goes in with `textContent`, `innerHTML` is used only to clear or for numeric bars, and colours pass a hex whitelist. It respects `prefers-reduced-motion`, has an `aria-live` status line, and degrades for narrow screens. When disconnected it freezes timers and labels the node "last seen here" rather than implying progress.

## Consequences
**Positive**
- Nothing to build or fetch; works offline.
- Event-driven state is testable in Node (ADR-0015).

**Negative**
- About 1,800 lines in one file is harder to navigate and review.
- Visual layout is only checked by manual browser QA (the harness says so).

## Alternatives considered
- A JS framework with a build step. Not evidenced as considered.

## Evidence
- loopscope/static/dashboard.html
- pyproject.toml (`[tool.setuptools.package-data]`)
- tests/dashboard_activity.cjs
- commits 1886c92, 0125e9b, a38579e, 0e2d8fa
