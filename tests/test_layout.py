"""Layout tests — longest-path layering and hub vs cycle (no fake supervisor)."""

from loopscope.layout import _layer, choose_pane, compute_layout, compute_mesh
from loopscope.topology import pack


def test_layer_is_longest_path():
    nodes = list("ABCDEF")
    edges = [("A", "C"), ("A", "B"), ("C", "E"), ("B", "D"), ("D", "E"), ("E", "F")]
    depth = _layer(nodes, edges)
    assert depth["E"] == 3
    assert depth["F"] == 4


def test_hub_requires_degree_gap():
    nodes = ["write", "critique", "research", "polish"]
    edges = [
        ("research", "write"),
        ("write", "critique"),
        ("critique", "write"),
        ("critique", "polish"),
    ]
    mesh = compute_mesh(nodes, edges)
    assert mesh["hub"] is None


def test_hub_promotes_clear_supervisor():
    nodes = ["boss", "w1", "w2"]
    edges = [
        ("boss", "w1"),
        ("w1", "boss"),
        ("boss", "w2"),
        ("w2", "boss"),
    ]
    mesh = compute_mesh(nodes, edges)
    assert mesh["hub"] == "boss"


def test_pipeline_with_terminals_is_flowchart():
    assert choose_pane(None, ["__start__", "__end__"]) == "flowchart"


def test_ralph_cycle_is_constellation():
    assert choose_pane(None, []) == "constellation"


def test_supervisor_hub_wins_over_terminals():
    assert choose_pane("boss", ["__start__", "__end__"]) == "constellation"


def test_pack_stride_like_pipeline_picks_flowchart():
    nodes = [
        {"id": "__start__", "label": "__start__", "kind": "start"},
        {"id": "generate_stride", "label": "generate_stride", "kind": "node"},
        {"id": "qa_stride", "label": "qa_stride", "kind": "node"},
        {"id": "generate_dread", "label": "generate_dread", "kind": "node"},
        {"id": "__end__", "label": "__end__", "kind": "end"},
    ]
    edges = [
        {"source": "__start__", "target": "generate_stride"},
        {"source": "generate_stride", "target": "qa_stride"},
        {"source": "qa_stride", "target": "generate_dread"},
        {"source": "generate_dread", "target": "__end__"},
    ]
    payload = pack(nodes, edges, title="STRIDE", source="langgraph")
    assert payload["mode"] == "flowchart"
    pos = payload["layout"]["positions"]
    assert pos["__start__"]["y"] < pos["generate_stride"]["y"] < pos["__end__"]["y"]
    assert pos["__start__"]["r"] < pos["generate_stride"]["r"]


def test_pack_ralph_cycle_picks_constellation():
    nodes = [{"id": p, "label": p, "kind": "node"} for p in ("plan", "edit", "test", "review")]
    edges = [
        {"source": "plan", "target": "edit"},
        {"source": "edit", "target": "test"},
        {"source": "test", "target": "review"},
        {"source": "review", "target": "plan", "conditional": True},
    ]
    payload = pack(nodes, edges, title="get the suite green", source="ralph")
    assert payload["mode"] == "constellation"
    assert payload["mesh"]["hub"] is None


def test_flowchart_layout_gives_radii():
    laid = compute_layout(
        ["__start__", "a", "__end__"],
        [("__start__", "a"), ("a", "__end__")],
        terminals=["__start__", "__end__"],
    )
    assert laid["positions"]["__start__"]["r"] == 34.0
    assert laid["positions"]["a"]["r"] == 58.0
