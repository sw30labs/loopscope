"""Replay + bind tests — torn JSONL, dead thread, origin allow-list."""

import json
import threading
from types import SimpleNamespace

from loopscope.replay import load_events
from loopscope.server import _origin_allowed, _wait_until_up


def test_load_events_skips_torn_and_replay(tmp_path):
    path = tmp_path / "tape.jsonl"
    path.write_text(
        json.dumps({"type": "log", "run_id": "r", "text": "ok"})
        + "\nnot-json\n"
        + json.dumps({"type": "replay", "events": []})
        + "\n"
        + '{"no":"type"}\n'
    )
    events = load_events(path)
    assert len(events) == 1
    assert events[0]["text"] == "ok"


def test_wait_until_up_dead_thread():
    server = SimpleNamespace(started=False)
    thread = threading.Thread(target=lambda: None)
    thread.start()
    thread.join()
    try:
        _wait_until_up(server, thread, timeout=0.3)
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")


def test_origin_same_host_ok():
    sock = SimpleNamespace(
        headers={"origin": "http://127.0.0.1:7788", "host": "127.0.0.1:7788"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert _origin_allowed(sock) is True


def test_origin_foreign_rejected():
    sock = SimpleNamespace(
        headers={"origin": "http://evil.example", "host": "127.0.0.1:7788"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert _origin_allowed(sock) is False


def test_origin_missing_loopback_ok():
    sock = SimpleNamespace(
        headers={"host": "127.0.0.1:7788"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert _origin_allowed(sock) is True


def test_origin_missing_lan_rejected():
    sock = SimpleNamespace(
        headers={"host": "192.168.1.5:7788"},
        client=SimpleNamespace(host="192.168.1.9"),
    )
    assert _origin_allowed(sock) is False
