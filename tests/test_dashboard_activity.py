"""Behavioral checks for live dashboard activity, using Node without npm deps.

The companion harness executes the actual dashboard script with a small DOM.
Visual appearance is intentionally left to browser QA.
"""

from pathlib import Path
import shutil
import subprocess

import pytest


NODE = shutil.which("node")
HARNESS = Path(__file__).with_name("dashboard_activity.cjs")
DASHBOARD = Path(__file__).parents[1] / "loopscope" / "static" / "dashboard.html"


@pytest.mark.skipif(NODE is None, reason="Node.js is required for dashboard checks")
@pytest.mark.parametrize(
    "scenario",
    [
        "waiting",
        "parallel",
        "arrival",
        "overlap",
        "completion",
        "replay",
        "handoff",
        "isolation",
    ],
)
def test_dashboard_activity(scenario):
    result = subprocess.run(
        [NODE, str(HARNESS), str(DASHBOARD), scenario],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
