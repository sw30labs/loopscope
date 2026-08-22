"""Replay a recorded run.

    loopscope.start(jsonl="runs/tonight.jsonl")   # record
    python -m loopscope.replay runs/tonight.jsonl --speed 8

Overnight Ralph loops finish while you are asleep. This plays the tape back at
whatever speed you can stand, so the post-mortem looks like the live view.

Author: Nic Cravino
Email: spidernic@me.com
LinkedIn: https://www.linkedin.com/in/nic-cravino
Created: August 21, 2026
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .bus import default_bus
from .events import REPLAY, RESERVED_KEYS, Event
from .server import start


def load_events(path: Path) -> list[dict]:
    """Read a JSONL tape; skip torn lines and nested replay frames."""
    events = []
    skipped = 0
    with path.open() as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(record, dict) or "type" not in record:
                skipped += 1
                continue
            if record["type"] == REPLAY:
                skipped += 1
                continue
            events.append(record)
    if skipped:
        print(f"skipped {skipped} corrupt or invalid line(s) in {path}", file=sys.stderr)
    return events


def main() -> None:
    parser = argparse.ArgumentParser(prog="loopscope.replay")
    parser.add_argument("path", type=Path, help="JSONL file written by EventBus(jsonl_path=...)")
    parser.add_argument("--speed", type=float, default=4.0, help="playback multiplier")
    parser.add_argument("--port", type=int, default=int(os.environ.get("LOOPSCOPE_PORT", "7788")))
    parser.add_argument("--max-gap", type=float, default=2.0, help="cap idle stretches, seconds")
    args = parser.parse_args()

    events = load_events(args.path)
    if not events:
        raise SystemExit(f"{args.path} has no events in it")

    open_browser = os.environ.get("LOOPSCOPE_NO_BROWSER", "").lower() not in ("1", "true", "yes")
    scope = start(port=args.port, open_browser=open_browser)
    time.sleep(1.0)  # let the browser attach before the first event lands

    bus = default_bus()
    fecha = events[0].get("ts", 0)
    for record in events:
        gap = max(0.0, record.get("ts", fecha) - fecha) / max(args.speed, 0.01)
        time.sleep(min(gap, args.max_gap))
        fecha = record.get("ts", fecha)
        payload = {k: v for k, v in record.items() if k not in RESERVED_KEYS}
        bus.publish(
            Event(record["type"], record.get("run_id", "replay"), payload, ts=time.time())
        )

    print(f"replayed {len(events)} events from {args.path}")
    scope.hold()


if __name__ == "__main__":
    main()
