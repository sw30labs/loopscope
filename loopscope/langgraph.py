"""LangGraph hook.

Two jobs: read the graph's shape once, then follow execution live.

Execution is followed with a plain LangChain callback handler rather than
`astream_events`, because callbacks fire for `.invoke()`, `.ainvoke()`,
`.stream()` and `.astream()` alike — the caller does not have to restructure
anything to be watched.

One gotcha this handles: every runnable *inside* a node (routers, chains, the
LLM itself) inherits `metadata["langgraph_node"]`, so keying on that alone
double-counts. Real node executions are the ones tagged `graph:step:N`.

Author: Nic Cravino
Email: spidernic@me.com
LinkedIn: https://www.linkedin.com/in/nic-cravino
Created: August 21, 2026
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import threading
import time
from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Tuple,
    get_args,
    get_origin,
    get_type_hints,
)
from uuid import UUID

from .bus import EventBus, default_bus
from .events import (
    EDGE,
    ITER_END,
    ITER_START,
    LOG,
    METRIC,
    NODE_END,
    NODE_ERROR,
    NODE_START,
    RUN_END,
    RUN_START,
    STATE,
    TOPOLOGY,
    Event,
    changed_keys,
    new_run_id,
    summarize_state,
    truncate,
)
from .topology import pack

try:  # LangChain is optional until you actually use this module.
    from langchain_core.callbacks import BaseCallbackHandler
except Exception:  # pragma: no cover
    class BaseCallbackHandler:  # type: ignore[no-redef]
        """Stand-in so importing loopscope never requires LangChain."""


START_NODE = "__start__"
END_NODE = "__end__"


# --- topology ----------------------------------------------------------------


def extract_topology(graph: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Pull nodes and edges out of a compiled (or raw) LangGraph object.

    Compiled `get_graph()` is not enough on its own. A conditional edge without
    a path_map is drawn as `node → __end__`, and every static edge behind that
    router disappears — so later chains show up as disconnected nodes. Overlay
    the original StateGraph (`compiled.builder`) and infer missing destinations
    from the router.
    """
    drawable_nodes, drawable_edges = _from_drawable(graph)
    builder = getattr(graph, "builder", None)
    if builder is None and _is_builder(graph):
        builder = graph
    builder_nodes, builder_edges = _from_builder(builder) if builder is not None else ([], [])
    return _merge_topology(builder_nodes, builder_edges, drawable_nodes, drawable_edges)


def _from_drawable(graph: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    getter = getattr(graph, "get_graph", None)
    if not callable(getter):
        return [], []
    try:
        drawable = getter()
    except Exception:
        return [], []
    if drawable is None:
        return [], []
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for node_id, node in getattr(drawable, "nodes", {}).items():
        nodes.append(
            {
                "id": str(node_id),
                "label": str(getattr(node, "name", node_id)),
                "kind": _classify(str(node_id)),
                "subtitle": _docline(getattr(node, "data", None)),
            }
        )
    for edge in getattr(drawable, "edges", []) or []:
        src, dst = _edge_pair(edge)
        if src is None or dst is None:
            continue
        edges.append(
            {
                "source": src,
                "target": dst,
                "conditional": bool(getattr(edge, "conditional", False)),
                "label": str(getattr(edge, "data", "") or getattr(edge, "label", "") or ""),
            }
        )
    return nodes, edges


def _is_builder(graph: Any) -> bool:
    """True for a StateGraph-shaped object, not a compiled Pregel."""
    if graph is None or getattr(graph, "builder", None) is not None:
        return False
    nodes = getattr(graph, "nodes", None)
    if not isinstance(nodes, dict):
        return False
    return hasattr(graph, "edges") or hasattr(graph, "branches")


def _from_builder(builder: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_map = getattr(builder, "nodes", {}) or {}
    known: Set[str] = {START_NODE, END_NODE}
    for node_id, spec in node_map.items():
        nid = str(node_id)
        known.add(nid)
        runnable = getattr(spec, "runnable", spec)
        nodes.append(
            {
                "id": nid,
                "label": nid,
                "kind": _classify(nid),
                "subtitle": _docline(runnable),
            }
        )

    for item in getattr(builder, "edges", []) or []:
        src, dst = _edge_pair(item)
        if src is None or dst is None:
            continue
        edges.append({"source": src, "target": dst, "conditional": False, "label": ""})

    for item in getattr(builder, "waiting_edges", []) or []:
        src, dst = _edge_pair(item)
        if src is not None and dst is not None:
            edges.append({"source": src, "target": dst, "conditional": False, "label": ""})
        elif isinstance(item, (tuple, list)) and len(item) == 2 and isinstance(item[0], (list, tuple)):
            for src in item[0]:
                edges.append(
                    {"source": str(src), "target": str(item[1]), "conditional": False, "label": ""}
                )

    for src, branches in (getattr(builder, "branches", {}) or {}).items():
        for name, branch in (branches or {}).items():
            for target, label in _branch_targets(branch, known, str(name)):
                edges.append(
                    {
                        "source": str(src),
                        "target": target,
                        "conditional": True,
                        "label": label,
                    }
                )
    return nodes, edges


def _branch_targets(branch: Any, known: Set[str], name: str) -> List[Tuple[str, str]]:
    ends = getattr(branch, "ends", None) or getattr(branch, "path_map", None) or {}
    if isinstance(ends, dict) and ends:
        out: List[Tuple[str, str]] = []
        for key, target in ends.items():
            if target is None:
                continue
            dest = _as_node_id(target, known)
            if dest is None:
                continue
            label = str(key) if key is not None else name
            out.append((dest, label))
        return out
    inferred = _infer_destinations(_callable_fn(getattr(branch, "path", None)), known)
    return [(dest, name) for dest in inferred]


def _callable_fn(obj: Any) -> Any:
    if obj is None:
        return None
    for attr in ("func", "afunc", "_func"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            return fn
    return obj if callable(obj) else None


def _infer_destinations(fn: Any, known: Set[str]) -> List[str]:
    """Destinations a router can return, when LangGraph was not told a path_map.

    Reads Literal[...] return hints and string constants / END names in the
    function body. Skips anything that is not a known node.
    """
    if fn is None:
        return []
    found: List[str] = []
    seen: Set[str] = set()

    def add(raw: Any) -> None:
        dest = _as_node_id(raw, known)
        if dest is None or dest in seen:
            return
        seen.add(dest)
        found.append(dest)

    try:
        hint = get_type_hints(fn).get("return")
    except Exception:
        hint = getattr(fn, "__annotations__", {}).get("return")
    origin = get_origin(hint)
    if origin is Literal or getattr(origin, "__name__", "") == "Literal":
        for arg in get_args(hint) or ():
            add(arg)

    # Bytecode first: inspect.getsource fails for stdin, exec, and some wrappers.
    code = getattr(fn, "__code__", None)
    if code is not None:
        stack = [code]
        while stack:
            block = stack.pop()
            for const in block.co_consts or ():
                if isinstance(const, str):
                    add(const)
                elif hasattr(const, "co_consts"):
                    stack.append(const)
            for name in block.co_names or ():
                if name in {"END", "START", END_NODE, START_NODE}:
                    add(name)

    try:
        src = textwrap.dedent(inspect.getsource(fn))
        tree = ast.parse(src)
    except Exception:
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            add(node.value)
        elif isinstance(node, ast.Name) and node.id in {"END", "START", END_NODE, START_NODE}:
            add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in {"END", "START"}:
            add(node.attr)
    return found


def _as_node_id(raw: Any, known: Set[str]) -> Optional[str]:
    if raw is None:
        return None
    value = str(raw)
    if value in {"END", END_NODE}:
        return END_NODE
    if value in {"START", START_NODE}:
        return START_NODE
    if value in known:
        return value
    return None


def _merge_topology(
    builder_nodes: List[Dict[str, Any]],
    builder_edges: List[Dict[str, Any]],
    drawable_nodes: List[Dict[str, Any]],
    drawable_edges: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_id: Dict[str, Dict[str, Any]] = {}

    def put(node: Dict[str, Any]) -> None:
        nid = node["id"]
        old = by_id.get(nid)
        if old is None:
            by_id[nid] = dict(node)
            return
        for key, value in node.items():
            if key == "kind" and value in {"start", "end"}:
                old[key] = value
            elif value and not old.get(key):
                old[key] = value

    for node in builder_nodes:
        put(node)
    for node in drawable_nodes:
        put(node)

    edges: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()

    def add_edge(edge: Dict[str, Any]) -> None:
        src, dst = edge["source"], edge["target"]
        key = (src, dst)
        if key in seen:
            return
        seen.add(key)
        edges.append(edge)
        for nid in (src, dst):
            if nid not in by_id:
                by_id[nid] = {"id": nid, "label": nid, "kind": _classify(nid)}

    builder_out: Set[str] = {e["source"] for e in builder_edges}
    for edge in builder_edges:
        add_edge(edge)
    for edge in drawable_edges:
        # get_graph() turns an unknown router into src → __end__. Drop that
        # stub when the builder already named real destinations for src.
        if (
            edge["target"] == END_NODE
            and edge["source"] in builder_out
            and not any(
                e["source"] == edge["source"] and e["target"] == END_NODE for e in builder_edges
            )
        ):
            continue
        add_edge(edge)

    _ensure_terminals(by_id, edges, seen)

    start, mid, end = [], [], []
    ordered_ids: List[str] = []
    for node in list(builder_nodes) + list(drawable_nodes):
        if node["id"] not in ordered_ids and node["id"] in by_id:
            ordered_ids.append(node["id"])
    for nid in list(by_id):
        if nid not in ordered_ids:
            ordered_ids.append(nid)
    for nid in ordered_ids:
        node = by_id[nid]
        kind = node.get("kind") or _classify(nid)
        node["kind"] = kind
        if kind == "start" or nid == START_NODE:
            start.append(node)
        elif kind == "end" or nid == END_NODE:
            end.append(node)
        else:
            mid.append(node)
    return start + mid + end, edges


def _ensure_terminals(
    by_id: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, Any]],
    seen: Set[Tuple[str, str]],
) -> None:
    if not edges:
        return
    if any(e["source"] == START_NODE or e["target"] == START_NODE for e in edges):
        if START_NODE not in by_id:
            by_id[START_NODE] = {"id": START_NODE, "label": START_NODE, "kind": "start"}
    has_out = {e["source"] for e in edges}
    sinks = [
        nid
        for nid, node in by_id.items()
        if (node.get("kind") or _classify(nid)) == "node" and nid not in has_out
    ]
    if not sinks and not any(e["target"] == END_NODE for e in edges):
        return
    if END_NODE not in by_id:
        by_id[END_NODE] = {"id": END_NODE, "label": END_NODE, "kind": "end"}
    for nid in sinks:
        key = (nid, END_NODE)
        if key in seen:
            continue
        seen.add(key)
        edges.append({"source": nid, "target": END_NODE, "conditional": False, "label": ""})


def _edge_pair(item: Any) -> Tuple[Optional[str], Optional[str]]:
    if isinstance(item, (tuple, list)) and len(item) >= 2 and not isinstance(item[0], (list, tuple)):
        return str(item[0]), str(item[1])
    src = getattr(item, "source", None) or getattr(item, "start", None)
    dst = getattr(item, "target", None) or getattr(item, "end", None)
    if src is None or dst is None:
        return None, None
    return str(src), str(dst)


def _docline(runnable: Any) -> str:
    """First line of the node function's docstring, used as its subtitle.

    Free labelling for anyone who already documents their nodes; silent when
    they do not.
    """
    if runnable is None:
        return ""
    for attr in ("func", "afunc", "_func"):
        fn = getattr(runnable, attr, None)
        if fn is None:
            continue
        doc = getattr(fn, "__doc__", None)
        if doc:
            return doc.strip().splitlines()[0].strip()[:48]
    return ""


def _classify(node_id: str) -> str:
    if node_id == START_NODE:
        return "start"
    if node_id == END_NODE:
        return "end"
    return "node"


def publish_topology(
    graph: Any,
    run_id: str,
    *,
    bus: Optional[EventBus] = None,
    title: Optional[str] = None,
    roles: Optional[Dict[str, str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    bus = bus or default_bus()
    nodes, edges = extract_topology(graph)
    payload = pack(
        nodes,
        edges,
        title=title or getattr(graph, "name", None) or "LangGraph",
        source="langgraph",
        roles=roles,
        extra=extra,
    )
    bus.publish(Event(TOPOLOGY, run_id, payload))


# --- live execution ----------------------------------------------------------


class LoopScopeCallback(BaseCallbackHandler):
    """Streams node starts, ends, errors, state writes and token usage.

    Pass it in `config={"callbacks": [...]}`, or let `attach()` build the
    config for you.
    """

    raise_error = False  # a broken dashboard must never kill the graph run

    def __init__(
        self,
        run_id: Optional[str] = None,
        *,
        bus: Optional[EventBus] = None,
        auto_iteration: bool = True,
        capture_state: bool = True,
    ):
        self.bus = bus or default_bus()
        self.run_id = run_id or new_run_id("lg")
        self.auto_iteration = auto_iteration
        self.capture_state = capture_state
        self._open: Dict[str, Dict[str, Any]] = {}
        self._last_node: Optional[str] = None
        self._state: Dict[str, Any] = {}
        self._iteration = 0
        self._iter_open = False
        self._root: Optional[str] = None
        self._depth = 0
        self._ended = False
        self._mu = threading.Lock()

    # -- helpers
    def _emit(self, type_: str, **payload: Any) -> None:
        self.bus.publish(Event(type_, self.run_id, payload))

    def _end_run(self, **payload: Any) -> None:
        if self._ended:
            return
        self._ended = True
        self._emit(RUN_END, **payload)

    @staticmethod
    def _is_node(tags: Optional[Sequence[str]], metadata: Optional[Dict[str, Any]]) -> bool:
        if not metadata or not metadata.get("langgraph_node"):
            return False
        return any(str(t).startswith("graph:step:") for t in (tags or []))

    def set_iteration(self, n: int) -> None:
        """Let an outer driver (a Ralph loop) own the iteration counter."""
        self._iteration = n
        self._last_node = None

    def begin_iteration(self, label: Optional[str] = None) -> None:
        self._iteration += 1
        self._iter_open = True
        self._emit(ITER_START, iteration=self._iteration, label=label or f"pass {self._iteration}")

    def end_iteration(self, **payload: Any) -> None:
        if not self._iter_open:
            return
        self._iter_open = False
        self._emit(ITER_END, iteration=self._iteration, **payload)

    # -- chain callbacks
    def on_chain_start(
        self,
        serialized: Optional[Dict[str, Any]],
        inputs: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        start_root = False
        node = None
        step = None
        last = None
        with self._mu:
            self._depth += 1
            if self._is_node(tags, metadata):
                node = str(metadata["langgraph_node"])
                step = metadata.get("langgraph_step")
                self._open[str(run_id)] = {"node": node, "t0": time.perf_counter(), "step": step}
                last = self._last_node
            elif parent_run_id is None and not (metadata or {}).get("langgraph_node"):
                self._root = str(run_id)
                self._last_node = None
                start_root = True
        if node:
            if last and last != node:
                self._emit(EDGE, source=last, target=node)
            elif not last:
                self._emit(EDGE, source=START_NODE, target=node)
            self._emit(NODE_START, node=node, step=step, iteration=self._iteration)
        elif start_root and self.auto_iteration:
            self.begin_iteration(kwargs.get("name"))

    def on_chain_end(
        self,
        outputs: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        with self._mu:
            self._depth = max(0, self._depth - 1)
            key = str(run_id)
            record = self._open.pop(key, None)
            is_root = key == self._root
            if is_root:
                self._root = None
            last = self._last_node
        if record:
            node = record["node"]
            elapsed_ms = (time.perf_counter() - record["t0"]) * 1000
            written: List[str] = []
            state_dict = _as_state_dict(outputs)
            if self.capture_state and state_dict is not None:
                with self._mu:
                    summary = summarize_state(state_dict)
                    written = changed_keys(self._state, summary)
                    self._state.update(summary)
                    self._last_node = node
                self._emit(
                    STATE,
                    node=node,
                    keys=written,
                    delta=summary,
                    iteration=self._iteration,
                )
            else:
                with self._mu:
                    self._last_node = node
            self._emit(
                NODE_END,
                node=node,
                ms=round(elapsed_ms, 2),
                step=record.get("step"),
                wrote=written,
                iteration=self._iteration,
            )
            return

        if is_root:
            if self.auto_iteration:
                self.end_iteration(status="ok")
            self._emit(EDGE, source=last or START_NODE, target=END_NODE)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        with self._mu:
            self._depth = max(0, self._depth - 1)
            record = self._open.pop(str(run_id), None)
            is_root = str(run_id) == self._root
            if is_root:
                self._root = None
        if record:
            self._emit(
                NODE_ERROR,
                node=record["node"],
                error=f"{type(error).__name__}: {error}"[:400],
                ms=round((time.perf_counter() - record["t0"]) * 1000, 2),
                iteration=self._iteration,
            )
        if is_root:
            if self.auto_iteration:
                self.end_iteration(status="error")
            self._end_run(status="error", error=f"{type(error).__name__}: {error}"[:400])

    # -- model + tool callbacks
    def on_llm_start(self, serialized, prompts, **kwargs: Any) -> None:
        self._emit(LOG, level="model", node=self._current_node(kwargs), text="prompting model")

    def on_chat_model_start(self, serialized, messages, **kwargs: Any) -> None:
        self._emit(LOG, level="model", node=self._current_node(kwargs), text="prompting model")

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        usage = _token_usage(response)
        if usage:
            self._emit(METRIC, name="tokens", node=self._current_node(kwargs), iteration=self._iteration, **usage)

    def on_tool_start(self, serialized: Optional[Dict[str, Any]], input_str: str, **kwargs: Any) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        self._emit(
            LOG,
            level="tool",
            node=self._current_node(kwargs),
            text=f"{name}({truncate(input_str, 120)})",
        )

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self._emit(LOG, level="error", node=self._current_node(kwargs), text=f"tool failed: {error}"[:300])

    def _current_node(self, kwargs: Dict[str, Any]) -> Optional[str]:
        metadata = kwargs.get("metadata") or {}
        return metadata.get("langgraph_node") or self._last_node


def _as_state_dict(outputs: Any) -> Optional[Dict[str, Any]]:
    """Node return value as a dict. Unwraps LangGraph Command.update."""
    if isinstance(outputs, dict):
        return outputs
    update = getattr(outputs, "update", None)
    if isinstance(update, dict):
        return update
    return None


def _token_usage(response: Any) -> Dict[str, int]:
    """Token counts live in one of three places depending on the provider."""
    salida: Dict[str, int] = {}
    llm_output = getattr(response, "llm_output", None) or {}
    usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
    if not usage:
        try:
            message = response.generations[0][0].message
            usage = getattr(message, "usage_metadata", None) or {}
        except Exception:
            usage = {}
    for source, target in (
        ("input_tokens", "input"),
        ("prompt_tokens", "input"),
        ("output_tokens", "output"),
        ("completion_tokens", "output"),
        ("total_tokens", "total"),
    ):
        if isinstance(usage, dict) and isinstance(usage.get(source), int):
            salida[target] = usage[source]
    if salida and "total" not in salida:
        salida["total"] = salida.get("input", 0) + salida.get("output", 0)
    return salida


# --- public surface ----------------------------------------------------------


def attach(
    graph: Any,
    *,
    bus: Optional[EventBus] = None,
    run_id: Optional[str] = None,
    title: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    auto_iteration: bool = True,
    roles: Optional[Dict[str, str]] = None,
    capture_state: bool = True,
) -> Dict[str, Any]:
    """Publish the graph shape and return a config that streams its execution.

        cfg = loopscope.attach(app)
        app.invoke(state, config=cfg)

    Any config you pass in is preserved; the handler is appended to it.
    """
    bus = bus or default_bus()
    handler = LoopScopeCallback(
        run_id=run_id, bus=bus, auto_iteration=auto_iteration, capture_state=capture_state
    )
    publish_topology(graph, handler.run_id, bus=bus, title=title, roles=roles)
    bus.publish(Event(RUN_START, handler.run_id, {"title": title or "LangGraph", "source": "langgraph"}))

    merged = dict(config or {})
    callbacks = list(merged.get("callbacks") or [])
    callbacks.append(handler)
    merged["callbacks"] = callbacks
    merged["_loopscope"] = handler  # handy escape hatch; LangChain ignores it
    return merged


def finish(config: Dict[str, Any], **payload: Any) -> None:
    """Close out a run started with `attach()` so the dashboard stops blinking."""
    handler = config.get("_loopscope")
    if isinstance(handler, LoopScopeCallback):
        handler.end_iteration(status=payload.get("status", "ok"))
        handler._end_run(**(payload or {"status": "ok"}))
