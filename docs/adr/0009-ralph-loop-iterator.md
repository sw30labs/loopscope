# ADR-0009: Model a Ralph loop as an iterator with a convergence signal, stall detection and flag-based termination

## Status
Accepted (retrospective, inferred 2026-11-02)

## Context
The ralph.py docstring: watching a Ralph loop is about whether each pass is better than the last "or is it thrashing", not where it is now.

## Decision
`RalphLoop` is iterated with `for it in loop`; each `Iteration` has timed `phase()` context managers, `log`, `metric`, `state`, `note` and `signal(value)`, the number the loop is driving to zero. The loop stops on `max_iters` (default 25), `max_seconds`, or no improvement in the signal for `stall_after` passes (default 4). `it.done()` and `loop.stop()` are flags, not exceptions, because an exception raised in a `for` body never reaches the generator; a `GeneratorExit` path records break/return/raise as done, error or abandoned. `StopLoop` can be raised from deep helpers and is recorded with its reason. `@ralph` wraps a function per pass, where a falsy return converges. `attach_graph()` lets a Ralph loop drive a LangGraph app on one timeline and own the iteration counter.

## Consequences
**Positive**
- Stall detection and the pass tape answer "is it converging".
- Cleanup and `run.end` are reliable however the loop exits (tested).

**Negative**
- `done()` doesn't exit immediately; callers must `break` (documented).
- The decorator treats `True` as "keep going", which is easy to misread (documented).

## Alternatives considered
- Raising an exception from `done()`, rejected in the docstring because it would skip the loop's own bookkeeping.

## Evidence
- loopscope/ralph.py
- examples/ralph_demo.py
- examples/langgraph_demo.py (`run_ralph`)
- tests/test_ralph.py
- tests/test_nested_graphs.py (`test_ralph_keeps_iteration_ownership_with_nested_graph`)
- commit 1886c92
