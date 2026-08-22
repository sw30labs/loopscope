"""RalphLoop tests — StopLoop must not look abandoned; max_seconds starts at iter."""

import time

from loopscope.bus import EventBus
from loopscope.ralph import RalphLoop, StopLoop


def _status(bus: EventBus, kind: str) -> str | None:
    rows = [e for e in bus.replay() if e["type"] == kind]
    if not rows:
        return None
    return rows[-1].get("status")


def test_stoploop_is_not_abandoned():
    bus = EventBus()
    loop = RalphLoop("obj", phases=["plan"], max_iters=5, stall_after=0, bus=bus)
    try:
        for _it in loop:
            raise StopLoop("from-helper")
    except StopLoop:
        pass
    assert _status(bus, "run.end") == "from-helper"
    assert _status(bus, "iter.end") == "done"
    assert loop.reason == "from-helper"


def test_max_seconds_starts_at_iter():
    bus = EventBus()
    loop = RalphLoop(
        "obj", phases=["plan"], max_iters=10, max_seconds=0.05, stall_after=0, bus=bus
    )
    time.sleep(0.08)
    n = 0
    for _it in loop:
        n += 1
        break
    assert n == 1


def test_signal_metric_is_flagged():
    bus = EventBus()
    loop = RalphLoop("obj", phases=["plan"], max_iters=1, stall_after=0, bus=bus)
    for it in loop:
        it.signal(3, name="failing")
        it.done("ok")
    metrics = [e for e in bus.replay() if e["type"] == "metric"]
    assert metrics
    assert metrics[0].get("signal") is True
    assert metrics[0]["name"] == "failing"
    assert metrics[0]["value"] == 3.0
