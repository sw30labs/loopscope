"""Assemble the one big event the dashboard draws everything from.

Both hooks — LangGraph and Ralph — end up here, so a graph run and a loop run
produce identically-shaped payloads and the client needs no special cases.

Author: Nic Cravino
Email: spidernic@me.com
LinkedIn: https://www.linkedin.com/in/nic-cravino
Created: August 21, 2026
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .layout import (
    choose_pane,
    compute_layout,
    compute_mesh,
    colors_for,
    layer_index,
    stages_from,
)

TERMINAL_KINDS = {"start", "end"}
TERMINAL_COLOR = "#aab2c5"


def pack(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    *,
    title: str,
    source: str,
    roles: Optional[Dict[str, str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # One payload the browser can draw without knowing LangGraph vs Ralph.
    roles = roles or {}
    ids = [n["id"] for n in nodes]
    pairs = [(e["source"], e["target"]) for e in edges]
    terminals = [n["id"] for n in nodes if n.get("kind") in TERMINAL_KINDS]

    depth = layer_index(ids, pairs)
    mesh = compute_mesh(ids, pairs, terminals=terminals, depth=depth)
    layered = compute_layout(ids, pairs, terminals=terminals)
    mode = choose_pane(mesh.get("hub"), terminals)
    back = {tuple(e) for e in layered["back_edges"]}

    # Colours: terminals stay grey so they read as punctuation, not as agents.
    hub = mesh.get("hub")
    assigned = colors_for([n["id"] for n in nodes if n["id"] not in terminals], hub)
    for node in nodes:
        if node["id"] in terminals:
            node["color"] = TERMINAL_COLOR
        else:
            node["color"] = assigned.get(node["id"], TERMINAL_COLOR)
        node["subtitle"] = roles.get(node["id"], node.get("subtitle") or "")
        node["layer"] = depth.get(node["id"], 0)
        node["hub"] = node["id"] == hub

    for edge in edges:
        edge["back"] = (edge["source"], edge["target"]) in back

    payload: Dict[str, Any] = {
        "title": title,
        "source": source,
        "nodes": nodes,
        "edges": edges,
        "mesh": mesh,
        "layout": layered,
        "mode": mode,
        "stages": stages_from(depth, terminals),
    }
    payload.update(extra or {})
    return payload
