"""Ralph loop hook.

A Ralph loop is the same agent run over and over against the same objective
until it stops finding things to fix. Watching one is a different problem from
watching a single graph pass: what you want to know is not "where is it now"
but "is this pass better than the last one, or is it thrashing".

So this module counts iterations, times phases, tracks a convergence signal you
choose, and shouts when the signal stops moving.

    loop = RalphLoop("fix the build", phases=["plan", "edit", "test"])
    for it in loop:
        with it.phase("plan"):
            plan = think()
        with it.phase("edit"):
            apply(plan)
        with it.phase("test") as p:
            failures = run_tests()
            p.log(f"{failures} failing")
        it.signal(failures)
        if failures == 0:
            it.done("green")

Author: Nic Cravino
Email: spidernic@me.com
LinkedIn: https://www.linkedin.com/in/nic-cravino
Created: August 21, 2026
"""

from __future__ import annotations

import contextvars
import functools
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

from .bus import EventBus, default_bus
from .events import (
    EDGE,
    ITER_END,
    ITER_START,
    LOG,
    METRIC,
    NODE_END,
    NODE_ERROR,
    NODE_START,
    RUN_END,
    RUN_START,
    STATE,
    TOPOLOGY,
    Event,
    new_run_id,
    summarize_state,
)
from .topology import pack

# Default phase names if the caller does not say — a tiny Ralph cycle.
DEFAULT_PHASES = ("plan", "act", "check")

_current_loop: contextvars.ContextVar[Optional["RalphLoop"]] = contextvars.ContextVar(
    "loopscope_ralph", default=None
)


class StopLoop(Exception):
    """Raised inside a loop body to end the run early.

    Marks the current iteration done before the exception leaves the `for`
    body, so the generator's close path emits `run.end` with this reason
    rather than `abandoned`.
    """

    def __init__(self, reason: str = "done"):
        super().__init__(reason)
        self.reason = reason
        loop = _current_loop.get()
        if loop is not None:
            loop.stop(reason)


class Phase:
    """One timed step inside an iteration."""

    def __init__(self, loop: "RalphLoop", name: str, iteration: int):
        self.loop = loop
        self.name = name
        self.iteration = iteration

    def log(self, text: str, level: str = "info") -> None:
        self.loop._emit(LOG, level=level, node=self.name, text=str(text)[:800], iteration=self.iteration)

    def metric(self, name: str, value: float) -> None:
        self.loop._emit(METRIC, name=name, value=value, node=self.name, iteration=self.iteration)


class Iteration:
    """Handle for the current pass. Yielded by iterating a `RalphLoop`."""

    def __init__(self, loop: "RalphLoop", n: int):
        self.loop = loop
        self.n = n
        self.started = time.time()
        self.phases_run: List[str] = []
        self._signal: Optional[float] = None
        self._note: Optional[str] = None
        self._done_reason: Optional[str] = None
        self._failed = False

    # -- narration
    def log(self, text: str, level: str = "info", node: Optional[str] = None) -> None:
        self.loop._emit(LOG, level=level, text=str(text)[:800], node=node, iteration=self.n)

    def metric(self, name: str, value: float, node: Optional[str] = None) -> None:
        self.loop._emit(METRIC, name=name, value=value, node=node, iteration=self.n)

    def state(self, state: Any, node: Optional[str] = None) -> None:
        self.loop._emit(STATE, delta=summarize_state(state), keys=[], node=node, iteration=self.n)

    def signal(self, value: float, name: str = "signal") -> None:
        """Report the number this loop is trying to drive to zero.

        Failing tests, unresolved TODOs, lint errors — whatever "not done yet"
        means for this job. It drives stall detection and the tape's height.
        """
        self._signal = float(value)
        self.loop._emit(
            METRIC,
            name=name,
            value=float(value),
            iteration=self.n,
            signal=True,
        )

    def note(self, text: str) -> None:
        """A short label for this pass, shown on the tape."""
        self._note = str(text)[:120]

    # -- phases
    @contextmanager
    def phase(self, name: str) -> Iterator[Phase]:
        previous = self.loop._last_phase
        if previous and previous != name:
            self.loop._emit(EDGE, source=previous, target=name)
        self.loop._emit(NODE_START, node=name, iteration=self.n)
        started = time.perf_counter()
        self.phases_run.append(name)
        try:
            yield Phase(self.loop, name, self.n)
        except StopLoop:
            self.loop._emit(NODE_END, node=name, ms=_ms(started), iteration=self.n)
            self.loop._last_phase = name
            raise
        except Exception as exc:
            self._failed = True
            self.loop._emit(
                NODE_ERROR,
                node=name,
                error=f"{type(exc).__name__}: {exc}"[:400],
                ms=_ms(started),
                iteration=self.n,
            )
            self.loop._last_phase = name
            raise
        else:
            self.loop._emit(NODE_END, node=name, ms=_ms(started), iteration=self.n)
            self.loop._last_phase = name

    # -- termination
    def done(self, reason: str = "converged") -> None:
        """Mark this as the last pass.

        Flag, not exception: an exception raised in a `for` body never reaches
        the generator that yielded it, so raising here would escape into the
        caller's code and skip the loop's own bookkeeping. The rest of this
        pass still runs — `break` immediately after if you want out now.
        """
        self._done_reason = reason


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


class RalphLoop:
    """Iterate until converged, out of patience, or out of time."""

    def __init__(
        self,
        objective: str,
        *,
        phases: Sequence[str] = DEFAULT_PHASES,
        max_iters: int = 25,
        max_seconds: Optional[float] = None,
        stall_after: int = 4,
        roles: Optional[Dict[str, str]] = None,
        bus: Optional[EventBus] = None,
        run_id: Optional[str] = None,
    ):
        self.objective = objective
        self.phases = list(phases)
        self.max_iters = max_iters
        self.max_seconds = max_seconds
        self.stall_after = stall_after
        self.roles = roles or {}
        self.bus = bus or default_bus()
        self.run_id = run_id or new_run_id("ralph")

        self.iteration = 0
        self.reason: Optional[str] = None
        self._started: Optional[float] = None
        self._last_phase: Optional[str] = None
        self._signals: List[Optional[float]] = []
        self._best: Optional[float] = None
        self._since_improvement = 0
        self._graph_handler = None
        self._current: Optional[Iteration] = None

    # -- plumbing
    def _emit(self, type_: str, **payload: Any) -> None:
        self.bus.publish(Event(type_, self.run_id, payload))

    def _publish_topology(self) -> None:
        """Draw the phases as a cycle, because that is what a Ralph loop is."""
        nodes = [{"id": p, "label": p, "kind": "node"} for p in self.phases]
        edges = [
            {"source": a, "target": b, "conditional": False, "label": ""}
            for a, b in zip(self.phases, self.phases[1:])
        ]
        if len(self.phases) > 1:
            edges.append(
                {
                    "source": self.phases[-1],
                    "target": self.phases[0],
                    "conditional": True,
                    "label": "not converged",
                }
            )
        self._emit(
            TOPOLOGY,
            **pack(
                nodes,
                edges,
                title=self.objective,
                source="ralph",
                roles=self.roles,
                extra={"max_iters": self.max_iters},
            ),
        )

    # -- LangGraph bridge
    def attach_graph(self, graph: Any, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Drive a LangGraph app from inside the loop, on one shared timeline.

            cfg = loop.attach_graph(app)
            for it in loop:
                result = app.invoke(state, config=cfg)

        The graph's nodes replace the phase list in the graph pane, and each
        node execution is filed under the current Ralph iteration.
        """
        from .langgraph import LoopScopeCallback, publish_topology

        handler = LoopScopeCallback(
            run_id=self.run_id, bus=self.bus, auto_iteration=False, capture_state=True
        )
        publish_topology(
            graph,
            self.run_id,
            bus=self.bus,
            title=self.objective,
            roles=self.roles,
            extra={"max_iters": self.max_iters},
        )
        self._graph_handler = handler

        merged = dict(config or {})
        callbacks = list(merged.get("callbacks") or [])
        callbacks.append(handler)
        merged["callbacks"] = callbacks
        return merged

    # -- iteration protocol
    def __iter__(self) -> Iterator[Iteration]:
        if self._graph_handler is None:
            self._publish_topology()
        self._started = time.time()
        token = _current_loop.set(self)
        try:
            self._emit(
                RUN_START,
                title=self.objective,
                source="ralph",
                max_iters=self.max_iters,
                phases=self.phases,
            )
            while True:
                if self.iteration >= self.max_iters:
                    self.reason = "max_iters"
                    break
                if self.max_seconds is not None and (
                    time.time() - self._started
                ) >= self.max_seconds:
                    self.reason = "timeout"
                    break

                self.iteration += 1
                previous_phase = self._last_phase
                self._last_phase = None
                if previous_phase and self.phases and previous_phase != self.phases[0]:
                    self._emit(EDGE, source=previous_phase, target=self.phases[0])
                if self._graph_handler is not None:
                    self._graph_handler.set_iteration(self.iteration)
                current = Iteration(self, self.iteration)
                self._current = current
                self._emit(
                    ITER_START,
                    iteration=self.iteration,
                    label=f"pass {self.iteration}",
                    max_iters=self.max_iters,
                )
                started = time.perf_counter()
                try:
                    yield current
                except GeneratorExit:
                    # The caller broke out, returned, or raised. This is the
                    # only signal a generator gets about either.
                    status = "done" if current._done_reason else ("error" if current._failed else "abandoned")
                    self._close_iteration(current, started, status)
                    self.reason = current._done_reason or self.reason or status
                    raise
                self._close_iteration(current, started, "error" if current._failed else "ok")
                if current._done_reason:
                    self.reason = current._done_reason
                    break
                if self._check_stall():
                    self.reason = "stalled"
                    break
        finally:
            _current_loop.reset(token)
            started = self._started or time.time()
            self._emit(
                RUN_END,
                status=self.reason or "finished",
                iterations=self.iteration,
                seconds=round(time.time() - started, 2),
            )

    def _close_iteration(self, current: Iteration, started: float, status: str, **extra: Any) -> None:
        self._signals.append(current._signal)
        if current._signal is not None:
            if self._best is None or current._signal < self._best:
                self._best = current._signal
                self._since_improvement = 0
            else:
                self._since_improvement += 1
        self._emit(
            ITER_END,
            iteration=current.n,
            status=status,
            ms=_ms(started),
            phases=current.phases_run,
            signal=current._signal,
            note=current._note,
            **extra,
        )

    def _check_stall(self) -> bool:
        if self.stall_after <= 0 or self._since_improvement < self.stall_after:
            return False
        self._emit(
            LOG,
            level="warn",
            text=f"no improvement in {self._since_improvement} passes — stopping",
            iteration=self.iteration,
        )
        return True

    def stop(self, reason: str = "stopped") -> None:
        """End after the current pass. Same flag semantics as `Iteration.done`."""
        self.reason = reason
        if self._current is not None:
            self._current._done_reason = reason

    # `with RalphLoop(...) as loop:` is optional — it just lets you raise
    # StopLoop from deep inside a helper without wrapping every call site.
    def __enter__(self) -> "RalphLoop":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if isinstance(exc, StopLoop):
            self.reason = exc.reason
            return True
        return False


def ralph(
    objective: Optional[str] = None,
    *,
    phases: Sequence[str] = DEFAULT_PHASES,
    max_iters: int = 25,
    max_seconds: Optional[float] = None,
    stall_after: int = 4,
    bus: Optional[EventBus] = None,
) -> Callable:
    """Decorator form: call the wrapped function once per pass.

        @ralph("keep fixing the build", phases=["edit", "test"])
        def pass_(it):
            ...
            return failures   # returning 0 / None / False ends the loop

    The function receives the `Iteration`. Return `0` / `0.0` / `None` / `False`
    to converge. `return True` means keep going (it is not a success signal).
    """

    def decorate(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            loop = RalphLoop(
                objective or fn.__name__,
                phases=phases,
                max_iters=max_iters,
                max_seconds=max_seconds,
                stall_after=stall_after,
                bus=bus,
            )
            result = None
            for iteration in loop:
                result = fn(iteration, *args, **kwargs)
                if isinstance(result, (int, float)) and not isinstance(result, bool):
                    iteration.signal(result)
                if not result:
                    iteration.done("converged")
                    break
            return result

        return wrapper

    return decorate
