"""LangGraph helper tests — docstring subtitles, Command.update unwrap, terminals."""

from typing import Literal

import pytest

from loopscope.langgraph import (
    END_NODE,
    START_NODE,
    _as_state_dict,
    _docline,
    extract_topology,
)


class _Runnable:
    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)


def test_docline_skips_none_func():
    class Node:
        func = None
        afunc = None
        _func = None

    assert _docline(Node()) == ""
    assert _docline(None) == ""


def test_docline_reads_first_line():
    def fn():
        """sources & facts

        more
        """

    assert _docline(_Runnable(func=fn)) == "sources & facts"


def test_as_state_dict_unwraps_command():
    class Command:
        def __init__(self, update):
            self.update = update

    assert _as_state_dict({"a": 1}) == {"a": 1}
    assert _as_state_dict(Command({"n": 1})) == {"n": 1}
    assert _as_state_dict("nope") is None


def test_uncompiled_fallback_adds_terminals():
    class Graph:
        nodes = {"research": object()}
        edges = [("__start__", "research"), ("research", "__end__")]
        branches = {}
        waiting_edges = []

    nodes, edges = extract_topology(Graph())
    ids = {n["id"] for n in nodes}
    assert "__start__" in ids
    assert "__end__" in ids
    assert any(e["source"] == "__start__" for e in edges)


class _Node:
    def __init__(self, name):
        self.name = name
        self.data = None


class _Edge:
    def __init__(self, source, target, conditional=False, data=None):
        self.source = source
        self.target = target
        self.conditional = conditional
        self.data = data


class _Drawable:
    def __init__(self, nodes, edges):
        self.nodes = {n: _Node(n) for n in nodes}
        self.edges = [_Edge(*e) if isinstance(e, tuple) else e for e in edges]


class _Branch:
    def __init__(self, path, ends=None):
        self.path = path
        self.ends = ends


def _pairs(edges):
    return {(e["source"], e["target"]) for e in edges}


def test_truncated_drawable_recovers_second_chain():
    """STRIDE-Lite shape: get_graph() keeps only the first router, then END.

    The DREAD / final / save chain is still on the compiled graph — just not
    reachable through a path_map-less conditional — so the mesh used to show
    those nodes with no start, no end, and no edges.
    """

    def should_qa_stride(state):
        return "generate_dread" if state.passed else "generate_stride"

    def should_qa_dread(state):
        return "final_qa" if state.passed else "generate_dread"

    class Builder:
        nodes = {
            "generate_stride": object(),
            "qa_stride": object(),
            "generate_dread": object(),
            "qa_dread": object(),
            "final_qa": object(),
            "save_model": object(),
        }
        edges = {
            (START_NODE, "generate_stride"),
            ("generate_stride", "qa_stride"),
            ("generate_dread", "qa_dread"),
            ("final_qa", "save_model"),
        }
        waiting_edges = []
        branches = {
            "qa_stride": {"should_qa_stride": _Branch(should_qa_stride)},
            "qa_dread": {"should_qa_dread": _Branch(should_qa_dread)},
        }

    class Compiled:
        builder = Builder()

        def get_graph(self):
            return _Drawable(
                [
                    START_NODE,
                    "generate_stride",
                    "qa_stride",
                    "generate_dread",
                    "qa_dread",
                    "final_qa",
                    "save_model",
                    END_NODE,
                ],
                [
                    (START_NODE, "generate_stride"),
                    ("generate_stride", "qa_stride"),
                    ("qa_stride", END_NODE),
                ],
            )

    nodes, edges = extract_topology(Compiled())
    ids = [n["id"] for n in nodes]
    kinds = {n["id"]: n["kind"] for n in nodes}
    pairs = _pairs(edges)

    assert kinds[START_NODE] == "start"
    assert kinds[END_NODE] == "end"
    assert pairs >= {
        (START_NODE, "generate_stride"),
        ("generate_stride", "qa_stride"),
        ("qa_stride", "generate_dread"),
        ("qa_stride", "generate_stride"),
        ("generate_dread", "qa_dread"),
        ("qa_dread", "final_qa"),
        ("qa_dread", "generate_dread"),
        ("final_qa", "save_model"),
        ("save_model", END_NODE),
    }
    assert ("qa_stride", END_NODE) not in pairs
    assert ids[0] == START_NODE
    assert ids[-1] == END_NODE


def test_path_map_conditionals_keep_end_and_continue():
    class Builder:
        nodes = {
            "select": object(),
            "work": object(),
            "save": object(),
        }
        edges = {(START_NODE, "select"), ("save", END_NODE)}
        waiting_edges = []
        branches = {
            "select": {
                "check_error": _Branch(
                    None,
                    ends={"continue": "work", "end": END_NODE},
                )
            },
            "work": {
                "check_error": _Branch(
                    None,
                    ends={"continue": "save", "end": END_NODE},
                )
            },
        }

    class Compiled:
        builder = Builder()

        def get_graph(self):
            return _Drawable(
                [START_NODE, "select", "work", "save", END_NODE],
                [
                    _Edge(START_NODE, "select"),
                    _Edge("select", "work", True, "continue"),
                    _Edge("select", END_NODE, True, "end"),
                    _Edge("work", "save", True, "continue"),
                    _Edge("work", END_NODE, True, "end"),
                    _Edge("save", END_NODE),
                ],
            )

    nodes, edges = extract_topology(Compiled())
    pairs = _pairs(edges)
    assert (START_NODE, "select") in pairs
    assert ("select", "work") in pairs
    assert ("select", END_NODE) in pairs
    assert ("work", "save") in pairs
    assert ("save", END_NODE) in pairs
    assert {n["kind"] for n in nodes if n["id"] == START_NODE} == {"start"}
    assert {n["kind"] for n in nodes if n["id"] == END_NODE} == {"end"}


def test_infers_router_from_bytecode_when_source_is_gone():
    ns: dict = {}
    exec(
        "def route(state):\n"
        "    return 'generate_dread' if state.ok else 'generate_stride'\n",
        ns,
    )
    route = ns["route"]

    class Graph:
        nodes = {
            "generate_stride": object(),
            "qa_stride": object(),
            "generate_dread": object(),
        }
        edges = {
            (START_NODE, "generate_stride"),
            ("generate_stride", "qa_stride"),
        }
        waiting_edges = []
        branches = {"qa_stride": {"route": _Branch(route)}}

    pairs = _pairs(extract_topology(Graph())[1])
    assert ("qa_stride", "generate_dread") in pairs
    assert ("qa_stride", "generate_stride") in pairs


def test_literal_return_is_enough_without_path_map():
    def route(state) -> Literal["write", "polish"]:
        return "polish"

    class Graph:
        nodes = {"write": object(), "critique": object(), "polish": object()}
        edges = {(START_NODE, "write"), ("write", "critique"), ("polish", END_NODE)}
        waiting_edges = []
        branches = {"critique": {"route": _Branch(route)}}

    nodes, edges = extract_topology(Graph())
    pairs = _pairs(edges)
    assert ("critique", "write") in pairs
    assert ("critique", "polish") in pairs
    assert ("polish", END_NODE) in pairs


def test_sink_without_end_edge_still_grows_a_terminal():
    class Graph:
        nodes = {"research": object(), "write": object()}
        edges = [(START_NODE, "research"), ("research", "write")]
        branches = {}
        waiting_edges = []

    nodes, edges = extract_topology(Graph())
    ids = {n["id"] for n in nodes}
    assert START_NODE in ids
    assert END_NODE in ids
    assert ("write", END_NODE) in _pairs(edges)


def test_real_langgraph_stride_and_scenario_shapes():
    pytest.importorskip("langgraph")
    from langgraph.graph import END, StateGraph
    from pydantic import BaseModel, ConfigDict

    class State(BaseModel):
        model_config = ConfigDict(extra="allow")
        passed: bool = False
        error: str | None = None

    def noop(state: State) -> dict:
        return {}

    def should_qa_stride(state: State) -> str:
        return "generate_dread" if state.passed else "generate_stride"

    def should_qa_dread(state: State) -> str:
        return "final_qa" if state.passed else "generate_dread"

    def check_error(state: State) -> str:
        return "end" if state.error else "continue"

    stride = StateGraph(State)
    for name in (
        "generate_stride",
        "qa_stride",
        "generate_dread",
        "qa_dread",
        "final_qa",
        "save_model",
    ):
        stride.add_node(name, noop)
    stride.set_entry_point("generate_stride")
    stride.add_edge("generate_stride", "qa_stride")
    stride.add_edge("generate_dread", "qa_dread")
    stride.add_edge("final_qa", "save_model")
    stride.add_conditional_edges("qa_stride", should_qa_stride)
    stride.add_conditional_edges("qa_dread", should_qa_dread)
    stride_pairs = _pairs(extract_topology(stride.compile())[1])
    assert (START_NODE, "generate_stride") in stride_pairs
    assert ("generate_dread", "qa_dread") in stride_pairs
    assert ("qa_stride", "generate_dread") in stride_pairs
    assert ("qa_dread", "final_qa") in stride_pairs
    assert ("save_model", END_NODE) in stride_pairs
    assert ("qa_stride", END_NODE) not in stride_pairs

    scenario = StateGraph(State)
    for name in ("select", "work", "save"):
        scenario.add_node(name, noop)
    scenario.set_entry_point("select")
    scenario.add_conditional_edges(
        "select", check_error, {"continue": "work", "end": END}
    )
    scenario.add_conditional_edges(
        "work", check_error, {"continue": "save", "end": END}
    )
    scenario.add_edge("save", END)
    scenario_pairs = _pairs(extract_topology(scenario.compile())[1])
    assert (START_NODE, "select") in scenario_pairs
    assert ("select", "work") in scenario_pairs
    assert ("select", END_NODE) in scenario_pairs
    assert ("work", "save") in scenario_pairs
    assert ("save", END_NODE) in scenario_pairs
