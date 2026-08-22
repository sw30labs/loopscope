"""A cyclic LangGraph app, watched two ways.

    python examples/langgraph_demo.py          # one graph run, self-counted passes
    python examples/langgraph_demo.py ralph    # a Ralph loop driving the graph

No API keys: the "model" is a sleep and a counter, so the wiring is what you
are looking at, not the model. Each node's docstring becomes its subtitle in
the mesh — that is where "sources & facts" under RESEARCH comes from.

Author: Nic Cravino
Email: spidernic@me.com
Created: August 21, 2026
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run without installing

import operator
import random
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

import loopscope


class State(TypedDict):
    goal: str
    draft: str
    critique: str
    score: float
    rounds: Annotated[int, operator.add]


def research(state: State) -> dict:
    """sources & facts"""
    time.sleep(random.uniform(0.3, 0.7))
    return {"draft": f"notes on {state['goal']}"}


def write(state: State) -> dict:
    """copy & drafts"""
    time.sleep(random.uniform(0.5, 1.1))
    return {"draft": f"draft v{state['rounds'] + 1} of {state['goal']}", "rounds": 1}


def critique(state: State) -> dict:
    """scores the draft"""
    time.sleep(random.uniform(0.4, 0.9))
    score = min(1.0, round(0.35 + 0.2 * state["rounds"] + random.uniform(-0.05, 0.1), 2))
    return {"critique": "tighten the opening" if score < 0.8 else "ship it", "score": score}


def polish(state: State) -> dict:
    """final pass"""
    time.sleep(random.uniform(0.2, 0.5))
    return {"draft": state["draft"] + " (polished)"}


def route(state: State) -> str:
    if state["score"] >= 0.8:
        return "polish"
    return "write" if state["rounds"] < 6 else "polish"


def build():
    # Toy graph: research → write → critique, loop until the score says ship it.
    graph = StateGraph(State)
    graph.add_node("research", research)
    graph.add_node("write", write)
    graph.add_node("critique", critique)
    graph.add_node("polish", polish)
    graph.add_edge(START, "research")
    graph.add_edge("research", "write")
    graph.add_edge("write", "critique")
    graph.add_conditional_edges("critique", route, {"write": "write", "polish": "polish"})
    graph.add_edge("polish", END)
    return graph.compile()


def run_plain(app):
    """One invocation. The handler counts the graph pass itself."""
    config = loopscope.attach(app, title="draft → critique → repeat")
    try:
        app.invoke({"goal": "the launch memo", "draft": "", "critique": "", "score": 0.0, "rounds": 0}, config=config)
        loopscope.finish(config, status="ok")
    except Exception:
        loopscope.finish(config, status="error")
        raise


def run_ralph(app):
    """A Ralph loop outside, the graph inside, one shared timeline."""
    loop = loopscope.RalphLoop("draft until it scores", max_iters=8, stall_after=4)
    config = loop.attach_graph(app)
    state = {"goal": "the launch memo", "draft": "", "critique": "", "score": 0.0, "rounds": 0}

    for it in loop:
        state = app.invoke(state, config=config)
        it.signal(round(1 - state["score"], 2), name="distance to 1.0")
        it.note(f"score {state['score']}")
        if state["score"] >= 0.9:
            it.done("good enough")
        state["rounds"] = 0  # fresh pass, same objective


if __name__ == "__main__":
    port = int(os.environ.get("LOOPSCOPE_PORT", "7788"))
    open_browser = os.environ.get("LOOPSCOPE_NO_BROWSER", "").lower() not in ("1", "true", "yes")
    scope = loopscope.start(port=port, open_browser=open_browser)
    app = build()
    time.sleep(1)  # give the browser a moment to attach
    if len(sys.argv) > 1 and sys.argv[1] == "ralph":
        run_ralph(app)
    else:
        run_plain(app)
    scope.hold()
