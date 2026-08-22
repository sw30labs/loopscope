"""Layered layout for the live graph pane.

Agent graphs are cyclic almost by definition — that is the whole point of a
Ralph loop — so a plain topological sort is not enough. Strip back-edges with a
DFS, layer what is left by longest path, then put the back-edges on screen as
return arcs, which is exactly how a person draws a loop on a whiteboard.

Doing this in Python rather than in the browser keeps the client dumb: it
receives coordinates and renders them.

Author: Nic Cravino
Email: spidernic@me.com
LinkedIn: https://www.linkedin.com/in/nic-cravino
Created: August 21, 2026
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


def _find_back_edges(nodes: Sequence[str], edges: Sequence[Tuple[str, str]]) -> Set[Tuple[str, str]]:
    """DFS grey-node edges — those are the cycles we draw as return arcs."""
    adjacency: Dict[str, List[str]] = defaultdict(list)
    for src, dst in edges:
        adjacency[src].append(dst)

    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    back: Set[Tuple[str, str]] = set()

    def visit(start: str) -> None:
        # Explicit stack: agent graphs are small but recursion limits are dumb.
        stack: List[Tuple[str, Iterable[str]]] = [(start, iter(adjacency[start]))]
        color[start] = GREY
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if color.get(child, WHITE) == GREY:
                    back.add((node, child))
                elif color.get(child, WHITE) == WHITE:
                    color[child] = GREY
                    stack.append((child, iter(adjacency[child])))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()

    for node in nodes:
        if color.get(node, WHITE) == WHITE:
            visit(node)
    return back


def _layer(nodes: Sequence[str], edges: Sequence[Tuple[str, str]]) -> Dict[str, int]:
    """Longest-path layering over the acyclic remainder."""
    incoming: Dict[str, List[str]] = {n: [] for n in nodes}
    outgoing: Dict[str, List[str]] = {n: [] for n in nodes}
    remaining: Dict[str, int] = {n: 0 for n in nodes}
    for src, dst in edges:
        if src in outgoing and dst in incoming:
            outgoing[src].append(dst)
            incoming[dst].append(src)
            remaining[dst] += 1

    layer = {n: 0 for n in nodes}
    ready = [n for n in nodes if remaining[n] == 0]
    seen: Set[str] = set()
    while ready:
        node = ready.pop(0)
        if node in seen:
            continue
        seen.add(node)
        for child in outgoing[node]:
            if layer[child] < layer[node] + 1:
                layer[child] = layer[node] + 1
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)
    # Anything trapped in a cycle island never got visited; park it after its
    # deepest known parent so it does not pile up on layer 0.
    for node in nodes:
        if node not in seen and incoming[node]:
            layer[node] = max(layer[p] for p in incoming[node]) + 1
    return layer


def _order_within_layers(
    layers: Dict[int, List[str]], edges: Sequence[Tuple[str, str]]
) -> Dict[int, List[str]]:
    """Two barycenter sweeps. Not optimal, but it unties the obvious knots."""
    parents: Dict[str, List[str]] = defaultdict(list)
    for src, dst in edges:
        parents[dst].append(src)

    for _ in range(2):
        for depth in sorted(layers)[1:]:
            index_above = {n: i for i, n in enumerate(layers[depth - 1])}
            def barycenter(node: str) -> float:
                positions = [index_above[p] for p in parents[node] if p in index_above]
                return sum(positions) / len(positions) if positions else 1e6
            layers[depth].sort(key=barycenter)
    return layers


def choose_pane(hub: Optional[str], terminals: Sequence[str] = ()) -> str:
    """Which live pane to draw.

    A supervisor (clear hub) and a Ralph cycle (no start/end) stay a
    constellation. A pipeline with terminals is a top-to-bottom flowchart —
    mermaid's grammar, our sprites.
    """
    if hub:
        return "constellation"
    if terminals:
        return "flowchart"
    return "constellation"


def compute_layout(
    nodes: Sequence[str],
    edges: Sequence[Tuple[str, str]],
    *,
    orientation: str = "vertical",
    node_gap: float = 200.0,
    layer_gap: float = 200.0,
    terminals: Sequence[str] = (),
) -> Dict[str, object]:
    """Return positions in abstract units plus which edges are loop-backs.

    The browser fits these to whatever space it has; nothing here assumes a
    pixel size.
    """
    nodes = list(dict.fromkeys(nodes))
    edges = [(s, d) for s, d in edges if s in set(nodes) and d in set(nodes)]
    if not nodes:
        return {"positions": {}, "back_edges": [], "width": 0, "height": 0}

    back = _find_back_edges(nodes, edges)
    forward = [e for e in edges if e not in back]
    depth = _layer(nodes, forward)

    layers: Dict[int, List[str]] = defaultdict(list)
    for node in nodes:
        layers[depth[node]].append(node)
    layers = _order_within_layers(dict(layers), forward)

    widest = max(len(v) for v in layers.values())
    positions: Dict[str, Dict[str, float]] = {}
    for level, members in layers.items():
        span = (len(members) - 1) * node_gap
        for i, node in enumerate(members):
            across = (widest - 1) * node_gap / 2 - span / 2 + i * node_gap
            along = level * layer_gap
            if orientation == "vertical":
                positions[node] = {"x": across, "y": along, "layer": level, "index": i}
            else:
                positions[node] = {"x": along, "y": across, "layer": level, "index": i}

    term = set(terminals)
    for node, pos in positions.items():
        pos["r"] = 34.0 if node in term else 58.0
        pos["hub"] = False

    xs = [p["x"] for p in positions.values()]
    ys = [p["y"] for p in positions.values()]
    return {
        "positions": positions,
        "back_edges": [list(e) for e in sorted(back)],
        "width": (max(xs) - min(xs)) or 1.0,
        "height": (max(ys) - min(ys)) or 1.0,
        "min_x": min(xs),
        "min_y": min(ys),
    }


# --- radial mesh -------------------------------------------------------------

PALETTE = [
    "#e8453c",  # reserved for the hub
    "#f59e0b",
    "#8b5cf6",
    "#06b6d4",
    "#2563eb",
    "#22c55e",
    "#ec4899",
    "#14b8a6",
    "#f97316",
    "#6366f1",
]


def compute_mesh(
    nodes: Sequence[str],
    edges: Sequence[Tuple[str, str]],
    *,
    terminals: Sequence[str] = (),
    depth: Optional[Dict[str, int]] = None,
) -> Dict[str, object]:
    """Arrange nodes as a constellation: one hub, everyone else in orbit.

    Supervisor-style graphs have an obvious centre — the node everything routes
    through — and reading that as a hub is truer to how the thing behaves than
    a top-to-bottom stack. A plain cycle (a Ralph loop's phases) has no such
    node, so the centre is left empty for the objective to sit in.
    """
    real = [n for n in nodes if n not in set(terminals)]
    if not real:
        return {"hub": None, "positions": {}, "radius": 0}

    degree: Dict[str, int] = {n: 0 for n in nodes}
    for src, dst in edges:
        if src in degree:
            degree[src] += 1
        if dst in degree:
            degree[dst] += 1

    busiest = max(real, key=lambda n: (degree[n], -real.index(n)))
    second = max((degree[n] for n in real if n != busiest), default=0)
    hub = busiest if degree[busiest] > 2 and degree[busiest] > second else None

    orbit = [n for n in real if n != hub] + [n for n in nodes if n in set(terminals)]
    if depth:
        orbit.sort(key=lambda n: (depth.get(n, 0), real.index(n) if n in real else 99))

    radius = max(232.0, 54.0 * len(orbit) / (2 * math.pi) + 190.0)
    positions: Dict[str, Dict[str, float]] = {}
    if hub:
        positions[hub] = {"x": 0.0, "y": 0.0, "r": 92.0, "hub": True, "angle": 0.0}

    step = (2 * math.pi) / max(len(orbit), 1)
    for i, node in enumerate(orbit):
        angle = -math.pi / 2 + i * step
        terminal = node in set(terminals)
        positions[node] = {
            "x": round(math.cos(angle) * radius, 2),
            "y": round(math.sin(angle) * radius, 2),
            "r": 34.0 if terminal else 58.0,
            "hub": False,
            "angle": round(angle, 4),
        }
    return {"hub": hub, "positions": positions, "radius": radius}


def colors_for(nodes: Sequence[str], hub: Optional[str]) -> Dict[str, str]:
    """Stable colour per node; the hub always takes the first slot."""
    assigned: Dict[str, str] = {}
    index = 1
    for node in nodes:
        if node == hub:
            assigned[node] = PALETTE[0]
        else:
            assigned[node] = PALETTE[index % len(PALETTE)]
            index += 1
            if index % len(PALETTE) == 0:
                index += 1
    return assigned


def stages_from(depth: Dict[str, int], terminals: Sequence[str] = ()) -> List[Dict[str, object]]:
    """Turn layers into the numbered stages shown in the stepper."""
    skip = set(terminals)
    buckets: Dict[int, List[str]] = defaultdict(list)
    for node, level in depth.items():
        if node not in skip:
            buckets[level].append(node)
    return [
        {"index": i + 1, "label": " · ".join(sorted(buckets[level])), "nodes": sorted(buckets[level])}
        for i, level in enumerate(sorted(buckets))
    ]


def layer_index(
    nodes: Sequence[str], edges: Sequence[Tuple[str, str]]
) -> Dict[str, int]:
    """Layer number per node, back-edges removed. Shared by mesh and stepper."""
    nodes = list(dict.fromkeys(nodes))
    back = _find_back_edges(nodes, edges)
    return _layer(nodes, [e for e in edges if e not in back])
