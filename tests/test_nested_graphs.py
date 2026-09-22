"""Nested topology and callbacks must describe the same work on one run."""
from typing import TypedDict

import pytest

pytest.importorskip("langgraph")
from langgraph.graph import START, END, StateGraph
from langgraph.config import get_config

import loopscope
from loopscope.bus import EventBus
from loopscope.langgraph import extract_topology


class State(TypedDict):
    n: int


def leaf():
    graph = StateGraph(State)
    graph.add_node("work", lambda s: {"n": s["n"] + 1})
    graph.add_edge(START, "work")
    graph.add_edge("work", END)
    return graph.compile()


def test_static_nested_nodes_have_unique_names_and_no_double_count():
    child = leaf()
    graph = StateGraph(State)
    graph.add_node("left", child)
    graph.add_node("right", child)
    graph.add_node("save", lambda s: {})
    graph.add_edge(START, "left")
    graph.add_edge("left", "right")
    graph.add_edge("right", "save")
    graph.add_edge("save", END)
    app = graph.compile()
    bus = EventBus()
    config = loopscope.attach(app, bus=bus)
    assert app.invoke({"n": 0}, config=config)["n"] == 2
    loopscope.finish(config)
    events = bus.replay()
    assert [e["node"] for e in events if e["type"] == "node.start"] == ["left/work", "right/work", "save"]
    assert len([e for e in events if e["type"] == "node.end"]) == 3
    topology = next(e for e in events if e["type"] == "graph.topology")
    pairs = {(e["source"], e["target"]) for e in topology["edges"]}
    assert all((e["source"], e["target"]) in pairs for e in events if e["type"] == "edge.traverse")
    assert len([e for e in events if e["type"] == "run.end"]) == 1


def test_wrapper_declarations_and_dynamic_discovery_share_namespace():
    for declared in (False, True):
        child = leaf()
        bus = EventBus()
        def wrapper(state):
            parent = get_config()
            config["_loopscope"].include_subgraph(child, parent["metadata"])
            return child.invoke(state)
        graph = StateGraph(State)
        graph.add_node("track", wrapper)
        graph.add_edge(START, "track")
        graph.add_edge("track", END)
        app = graph.compile()
        if declared:
            app.loopscope_subgraphs = {"track": child}
        config = loopscope.attach(app, bus=bus)
        app.invoke({"n": 0}, config=config)
        loopscope.finish(config)
        events = bus.replay()
        assert [e["node"] for e in events if e["type"] == "node.end"] == ["track/work"]
        topology = next(e for e in events if e["type"] == "graph.topology")
        assert "track/work" in {n["id"] for n in topology["nodes"]}
        assert "track" not in {n["id"] for n in topology["nodes"]}


def test_repeated_subgraph_loops_are_traversed():
    graph = StateGraph(State)
    graph.add_node("cycle", leaf())
    graph.add_edge(START, "cycle")
    graph.add_conditional_edges("cycle", lambda s: "cycle" if s["n"] < 3 else END,
                                {"cycle": "cycle", END: END})
    app = graph.compile()
    bus = EventBus()
    config = loopscope.attach(app, bus=bus)
    app.invoke({"n": 0}, config=config)
    loopscope.finish(config)
    events = bus.replay()
    assert len([e for e in events if e["type"] == "node.start" and e["node"] == "cycle/work"]) == 3
    assert sum(e["type"] == "edge.traverse" and e["source"] == "cycle/__end__" and
               e["target"] == "cycle/__start__" for e in events) == 2


def test_conditional_entry_router_is_not_counted_as_a_work_node():
    child = StateGraph(State)
    child.add_node("work", lambda s: {"n": 1})
    child.add_conditional_edges(START, lambda s: "work", {"work": "work"})
    child.add_edge("work", END)
    outer = StateGraph(State)
    outer.add_node("writer", child.compile())
    outer.add_edge(START, "writer")
    outer.add_edge("writer", END)
    bus = EventBus()
    app = outer.compile()
    config = loopscope.attach(app, bus=bus)
    app.invoke({"n": 0}, config=config)
    loopscope.finish(config)
    assert [e["node"] for e in bus.replay() if e["type"] == "node.start"] == ["writer/work"]


def test_custom_usage_does_not_invent_unreported_tokens():
    bus = EventBus()
    config = loopscope.attach(leaf(), bus=bus)
    handler = config["_loopscope"]
    meta = {"langgraph_node": "work", "langgraph_checkpoint_ns": "track:uuid|work:uuid"}
    handler.on_custom_event("loopscope", {"kind": "tokens", "input": -1, "output": True, "total": "12"}, metadata=meta)
    assert not any(e["type"] == "metric" for e in bus.replay())
    handler.on_custom_event("loopscope", {"kind": "tokens", "input": 7, "output": 9}, metadata=meta)
    metric = next(e for e in bus.replay() if e["type"] == "metric")
    assert metric["node"] == "track/work" and metric["total"] == 16


def test_ralph_keeps_iteration_ownership_with_nested_graph():
    graph = StateGraph(State)
    graph.add_node("inner", leaf())
    graph.add_edge(START, "inner")
    graph.add_edge("inner", END)
    app = graph.compile()
    bus = EventBus()
    loop = loopscope.RalphLoop("check nested", max_iters=2, bus=bus)
    config = loop.attach_graph(app)
    for iteration in loop:
        app.invoke({"n": 0}, config=config)
        iteration.done("done")
    events = bus.replay()
    assert [e["node"] for e in events if e["type"] == "node.start"] == ["inner/work"]
    assert len([e for e in events if e["type"] == "iter.start"]) == 1
    assert len([e for e in events if e["type"] == "run.end"]) == 1
    assert next(e for e in events if e["type"] == "graph.topology")["max_iters"] == 2


@pytest.mark.parametrize("capture_errors", [True, False])
def test_exception_bodies_can_be_omitted_without_changing_failure(capture_errors):
    def fail(state):
        raise ValueError("private rejected reply")
    child = StateGraph(State)
    child.add_node("fail", fail)
    child.add_edge(START, "fail")
    child.add_edge("fail", END)
    graph = StateGraph(State)
    graph.add_node("child", child.compile())
    graph.add_edge(START, "child")
    graph.add_edge("child", END)
    app = graph.compile()
    bus = EventBus()
    config = loopscope.attach(app, bus=bus, capture_errors=capture_errors)
    with pytest.raises(ValueError, match="private rejected reply"):
        app.invoke({"n": 0}, config=config)
    loopscope.finish(config, status="error")
    events = bus.replay()
    assert ("private rejected reply" in str(events)) == capture_errors
    assert any(e["type"] == "node.error" and e["node"] == "child/fail" for e in events)
    assert len([e for e in events if e["type"] == "run.end"]) == 1


def test_parallel_discovered_graphs_keep_both_branches():
    from threading import Barrier
    barrier = Barrier(2)
    child = leaf()
    bus = EventBus()
    def wrapper(state):
        barrier.wait(timeout=5)
        parent = get_config()
        config['_loopscope'].include_subgraph(child, parent['metadata'])
        child.invoke(state)
        return {}  # Parallel siblings deliberately don't write the same key.
    outer = StateGraph(State)
    outer.add_node('left', wrapper)
    outer.add_node('right', wrapper)
    outer.add_edge(START, 'left')
    outer.add_edge(START, 'right')
    outer.add_edge('left', END)
    outer.add_edge('right', END)
    app = outer.compile()
    config = loopscope.attach(app, bus=bus)
    app.invoke({'n': 0}, config=config)
    loopscope.finish(config)
    topology = next(e for e in bus.replay() if e['type'] == 'graph.topology')
    names = {n['id'] for n in topology['nodes']}
    assert {'left/work', 'right/work'} <= names
    assert {e['node'] for e in bus.replay() if e['type'] == 'node.end'} == {'left/work', 'right/work'}
