"""Event envelope + redact/truncate tests (dashboard is a watch UI, not an audit)."""

from loopscope.events import Event, summarize_state, truncate


def test_as_dict_envelope_wins():
    d = Event("log", "r", {"type": "hijack", "text": "x", "seq": 99}).as_dict()
    assert d["type"] == "log"
    assert d["seq"] == 0
    assert d["run_id"] == "r"
    assert d["text"] == "x"


def test_summarize_state_caps_top_level_keys():
    state = {f"k{i}": i for i in range(100)}
    out = summarize_state(state)
    assert len(out) == 40


def test_summarize_redacts_secret_keys():
    out = summarize_state({"openai_api_key": "sk-live-secret", "ok": 1})
    assert out["openai_api_key"] == "—"
    assert out["ok"] == 1


def test_truncate_nested_list_cap():
    out = truncate(list(range(30)))
    assert len(out) == 13
    assert "more" in out[-1]
