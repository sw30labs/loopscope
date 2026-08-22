"""In-process event bus.

Producers (LangGraph callbacks, Ralph loops) are usually on some other thread
than the dashboard's event loop — sync `.invoke()` on the main thread, an async
app on its own loop, a worker pool, whatever. So `publish()` has to be callable
from anywhere and must never block or raise into the caller's hot path.

The bus keeps a ring buffer (default 4000 events; topology is pinned separately)
so a late browser still gets recent history plus the graph to draw. Overnight
loops that wrap the buffer lose early log lines; pass `jsonl=` for a full tape.

Author: Nic Cravino
Email: spidernic@me.com
LinkedIn: https://www.linkedin.com/in/nic-cravino
Created: August 21, 2026
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import queue as queue_mod
import threading
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from .events import REPLAY, Event


class EventBus:
    def __init__(self, buffer_size: int = 4000, jsonl_path: Optional[str] = None):
        self._buffer: Deque[Event] = deque(maxlen=buffer_size)
        self._subscribers: Set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._seq = itertools.count(1)
        self._jsonl: Optional[Path] = None
        self._record_q: Optional[queue_mod.SimpleQueue] = None
        # Latest topology per run, kept out of the ring buffer so it can never
        # be evicted — without it the browser has no graph to draw on.
        self._topology: Dict[str, Event] = {}
        if jsonl_path:
            self.set_jsonl(jsonl_path)

    # -- wiring ---------------------------------------------------------------

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called by the server once its event loop is running."""
        with self._lock:
            self._loop = loop

    def set_jsonl(self, path: str) -> None:
        """Attach a JSONL recording path. No-op if already this path; error if another."""
        target = Path(path)
        with self._lock:
            if self._jsonl is not None:
                if self._jsonl == target or self._same_file(self._jsonl, target):
                    return
                raise ValueError(f"bus already recording to {self._jsonl}")
            target.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                pass
            os.close(fd)
            self._jsonl = target
            self._record_q = queue_mod.SimpleQueue()
            thread = threading.Thread(
                target=self._jsonl_writer, name="loopscope-jsonl", daemon=True
            )
            thread.start()

    @staticmethod
    def _same_file(a: Path, b: Path) -> bool:
        try:
            return a.resolve() == b.resolve()
        except OSError:
            return False

    def _jsonl_writer(self) -> None:
        q, path = self._record_q, self._jsonl
        if q is None or path is None:
            return
        while True:
            item = q.get()
            if item is None:
                break
            try:
                with path.open("a") as fh:
                    fh.write(json.dumps(item, default=str) + "\n")
            except Exception:
                pass

    # -- producing ------------------------------------------------------------

    def publish(self, event: Event) -> None:
        """Fire-and-forget. Safe from any thread, including inside a callback."""
        if event.type == REPLAY:
            return
        record = None
        with self._lock:
            event.seq = next(self._seq)
            if event.type == "graph.topology":
                self._topology[event.run_id] = event
            else:
                self._buffer.append(event)
            loop = self._loop
            subscribers = list(self._subscribers)
            if self._record_q is not None:
                record = event.as_dict()
        if record is not None:
            try:
                self._record_q.put(record)
            except Exception:
                pass
        if not loop or not subscribers:
            return
        try:
            loop.call_soon_threadsafe(self._fanout, event, subscribers)
        except RuntimeError:
            # Loop already closed — the dashboard went away. Not our problem.
            pass

    def _fanout(self, event: Event, subscribers: List[asyncio.Queue]) -> None:
        for q in subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer: drop the oldest rather than stall the producer.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    # -- consuming ------------------------------------------------------------

    def subscribe(self, maxsize: int = 1000) -> asyncio.Queue:
        queue, _, _ = self.subscribe_and_replay(maxsize=maxsize)
        return queue

    def subscribe_and_replay(
        self, maxsize: int = 1000
    ) -> Tuple[asyncio.Queue, List[Dict[str, Any]], int]:
        """Register a subscriber and snapshot under the same lock.

        Live events with seq <= the snapshot's max seq must be skipped by the
        sender; they are already in the snapshot.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.add(queue)
            topo = list(self._topology.values())
            events = list(self._buffer)
        snapshot = [e.as_dict() for e in sorted(topo + events, key=lambda e: e.seq)]
        last_seq = max((row.get("seq") or 0 for row in snapshot), default=0)
        return queue, snapshot, last_seq

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    def replay(self) -> List[Dict[str, Any]]:
        """Everything a fresh browser needs to reconstruct the current run."""
        with self._lock:
            topo = list(self._topology.values())
            events = list(self._buffer)
        return [e.as_dict() for e in sorted(topo + events, key=lambda e: e.seq)]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._topology.clear()


# A module-level default so `loopscope.start()` + `@ralph()` just work together
# without the caller having to thread a bus object through every function.
_default_bus: Optional[EventBus] = None
_default_lock = threading.Lock()


def default_bus() -> EventBus:
    global _default_bus
    with _default_lock:
        if _default_bus is None:
            _default_bus = EventBus()
        return _default_bus


def set_default_bus(bus: EventBus) -> None:
    global _default_bus
    with _default_lock:
        _default_bus = bus
