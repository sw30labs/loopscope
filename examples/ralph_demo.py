"""A Ralph loop with no LangGraph in sight.

    python examples/ralph_demo.py

Stands in for the real thing — an agent that keeps editing until the tests go
green — with sleeps instead of model calls so you can watch the dashboard.

Author: Nic Cravino
Email: spidernic@me.com
Created: August 21, 2026
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run without installing

import random
import time

import loopscope

port = int(os.environ.get("LOOPSCOPE_PORT", "7788"))
open_browser = os.environ.get("LOOPSCOPE_NO_BROWSER", "").lower() not in ("1", "true", "yes")
scope = loopscope.start(port=port, open_browser=open_browser)

loop = loopscope.RalphLoop(
    "get the suite green",
    phases=["plan", "edit", "test", "review"],
    max_iters=14,
    stall_after=5,
    roles={
        "plan": "pick the cheapest fixes",
        "edit": "apply the patch",
        "test": "run the suite",
        "review": "log the diff",
    },
)

failures = 9

for it in loop:
    with it.phase("plan") as p:
        time.sleep(random.uniform(0.3, 0.8))
        p.log(f"{failures} failing — picking the two cheapest")

    with it.phase("edit") as p:
        time.sleep(random.uniform(0.6, 1.4))
        touched = random.randint(1, 3)
        p.log(f"patched {touched} file{'s' if touched > 1 else ''}")

    with it.phase("test") as p:
        time.sleep(random.uniform(0.8, 1.6))
        # Mostly downhill, occasionally a regression — the interesting shape.
        failures = max(0, failures - random.choice([2, 1, 1, 0, -1]))
        p.log(f"{failures} failing", level="warn" if failures else "info")

    if failures:
        with it.phase("review") as p:
            time.sleep(random.uniform(0.2, 0.5))
            p.log("logged the diff, going round again")

    it.signal(failures, name="failing tests")
    it.note(f"{failures} failing")

    if failures == 0:
        it.done("suite green")
        break

print(f"finished: {loop.reason} after {loop.iteration} passes")
scope.hold()
