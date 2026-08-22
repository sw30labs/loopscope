"""Bus tests — ring buffer, subscribe/replay race, jsonl mode 0600."""

import asyncio
import json
import os
import stat
import time

from loopscope.bus import EventBus
from loopscope.events import Event, LOG, REPLAY


def test_publish_drops_replay_type():
    bus = EventBus()
    bus.publish(Event(REPLAY, "r", {"events": []}))
    assert bus.replay() == []


def test_subscribe_and_replay_skips_in_flight_duplicates():
    async def main():
        bus = EventBus()
        bus.bind_loop(asyncio.get_running_loop())
        bus.publish(Event(LOG, "r", {"text": "hist"}))
        await asyncio.sleep(0)
        queue, snapshot, last_seq = bus.subscribe_and_replay()
        bus.publish(Event(LOG, "r", {"text": "race"}))
        await asyncio.sleep(0)
        live = []
        while True:
            try:
                ev = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if ev.seq <= last_seq:
                continue
            live.append(ev)
        snap_texts = [e.get("text") for e in snapshot]
        live_texts = [e.payload.get("text") for e in live]
        assert "hist" in snap_texts
        assert "race" in snap_texts or "race" in live_texts
        assert not (set(snap_texts) & set(live_texts))

    asyncio.run(main())


def test_jsonl_mode_0600(tmp_path):
    path = tmp_path / "run.jsonl"
    bus = EventBus(jsonl_path=str(path))
    bus.publish(Event(LOG, "r", {"text": "hi"}))
    deadline = time.time() + 2
    while time.time() < deadline and (not path.exists() or path.stat().st_size == 0):
        time.sleep(0.02)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    line = path.read_text().strip().splitlines()[0]
    row = json.loads(line)
    assert row["type"] == "log"
    assert row["text"] == "hi"


def test_set_jsonl_same_path_ok(tmp_path):
    path = tmp_path / "run.jsonl"
    bus = EventBus()
    bus.set_jsonl(str(path))
    bus.set_jsonl(str(path))


def test_set_jsonl_other_path_raises(tmp_path):
    bus = EventBus()
    bus.set_jsonl(str(tmp_path / "a.jsonl"))
    try:
        bus.set_jsonl(str(tmp_path / "b.jsonl"))
    except ValueError:
        return
    raise AssertionError("expected ValueError")
