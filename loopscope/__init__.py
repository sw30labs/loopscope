"""loopscope — live view of LangGraph state graphs and Ralph loops.

    import loopscope

    scope = loopscope.start(open_browser=True)      # dashboard on :7788

    cfg = loopscope.attach(app)                     # LangGraph
    app.invoke(state, config=cfg)

    for it in loopscope.RalphLoop("fix the build"): # Ralph loop
        ...

Both hooks write to the same bus, so a Ralph loop driving a LangGraph app shows
up as one timeline: graph nodes on the left, iterations on the tape.

Author: Nic Cravino
Email: spidernic@me.com
LinkedIn: https://www.linkedin.com/in/nic-cravino
Created: August 21, 2026
"""

from .bus import EventBus, default_bus, set_default_bus
from .events import Event
from .ralph import Iteration, Phase, RalphLoop, StopLoop, ralph
from .server import Dashboard, create_app, start

__version__ = "0.1.0b1"

__all__ = [
    "start",
    "Dashboard",
    "create_app",
    "EventBus",
    "default_bus",
    "set_default_bus",
    "Event",
    "RalphLoop",
    "Iteration",
    "Phase",
    "StopLoop",
    "ralph",
    "attach",
    "finish",
    "log",
    "metric",
]


def attach(graph, **kwargs):
    """LangGraph hook. Imported lazily so LangChain stays optional."""
    from .langgraph import attach as _attach

    return _attach(graph, **kwargs)


def finish(config, **payload):
    from .langgraph import finish as _finish

    return _finish(config, **payload)


def log(text: str, level: str = "info", run_id: str = "manual", **payload):
    """Drop a line onto the stream from anywhere."""
    from .events import LOG, RESERVED_KEYS

    extra = {k: v for k, v in payload.items() if k not in RESERVED_KEYS}
    default_bus().publish(
        Event(LOG, run_id, {"level": level, "text": str(text)[:800], **extra})
    )


def metric(name: str, value: float, run_id: str = "manual", **payload):
    from .events import METRIC, RESERVED_KEYS

    extra = {k: v for k, v in payload.items() if k not in RESERVED_KEYS}
    default_bus().publish(
        Event(METRIC, run_id, {"name": name, "value": value, **extra})
    )
