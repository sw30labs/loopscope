"""Event vocabulary shared by the instrumentation, the bus and the browser.

One flat envelope so the websocket payload stays trivial to parse on the
client and trivial to persist to a JSONL file for replay later.

Author: Nic Cravino
Email: spidernic@me.com
LinkedIn: https://www.linkedin.com/in/nic-cravino
Created: August 21, 2026
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Event types (plain strings — the dashboard switches on these directly)

RUN_START = "run.start"
RUN_END = "run.end"
TOPOLOGY = "graph.topology"  # full node/edge list + precomputed layout
NODE_START = "node.start"
NODE_END = "node.end"
NODE_ERROR = "node.error"
EDGE = "edge.traverse"
ITER_START = "iter.start"
ITER_END = "iter.end"
STATE = "state.delta"
LOG = "log"
METRIC = "metric"

# Client-internal; never a bus event. Replay CLI and publish() reject it.
REPLAY = "replay"

RESERVED_KEYS = frozenset({"type", "run_id", "ts", "seq"})
_SECRET_KEY = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|bearer|cookie)",
    re.I,
)


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


@dataclass(slots=True)
class Event:
    """A single thing that happened, somewhere, at some time."""

    type: str
    run_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    seq: int = 0  # stamped by the bus on publish

    def as_dict(self) -> Dict[str, Any]:
        # Envelope keys last so a payload cannot clobber type/run_id/ts/seq.
        body = {k: v for k, v in self.payload.items() if k not in RESERVED_KEYS}
        return {
            **body,
            "type": self.type,
            "run_id": self.run_id,
            "ts": self.ts,
            "seq": self.seq,
        }


def _short_key(key: Any) -> str:
    text = str(key)
    return text if len(text) <= 64 else text[:61] + "..."


def _redact(key: str, value: Any) -> Any:
    return "—" if _SECRET_KEY.search(key) else value


def truncate(value: Any, limit: int = 600) -> Any:
    """Shrink anything headed for the wire.

    State objects in a long-running loop get big fast, and nobody reads a
    40 KB dict in a log pane. Keep shape, drop bulk.
    """
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"… (+{len(value) - limit} chars)"
    if isinstance(value, dict):
        return {
            _short_key(k): truncate(_redact(str(k), v), limit // 2)
            for k, v in list(value.items())[:40]
        }
    if isinstance(value, (list, tuple)):
        head = [truncate(v, limit // 2) for v in list(value)[:12]]
        if len(value) > 12:
            head.append(f"… (+{len(value) - 12} more)")
        return head
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "…"


def summarize_state(state: Any, limit: int = 600) -> Dict[str, Any]:
    """Turn a graph state into something the dashboard can render."""
    if isinstance(state, dict):
        return {
            _short_key(k): truncate(_redact(str(k), v), limit)
            for k, v in list(state.items())[:40]
        }
    if state is None:
        return {}
    for attr in ("model_dump", "dict", "_asdict"):
        fn = getattr(state, attr, None)
        if callable(fn):
            try:
                return summarize_state(fn(), limit)
            except Exception:  # pragma: no cover - defensive
                break
    if hasattr(state, "__dict__"):
        return summarize_state(vars(state), limit)
    return {"value": truncate(state, limit)}


def changed_keys(before: Optional[Dict[str, Any]], after: Dict[str, Any]) -> list[str]:
    """Which keys a node actually wrote. Reprs, so it is cheap and shallow."""
    if not before:
        return sorted(after.keys())
    salida = []
    for key, value in after.items():
        if key not in before or repr(before[key]) != repr(value):
            salida.append(key)
    return sorted(salida)
