// Run the shipped inline script; expose its closure only in this test VM.
// This DOM covers script behavior, not layout, CSS, or browser accessibility.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.attributes = {};
    this.style = { setProperty(name, value) { this[name] = value; } };
    this.dataset = {};
    this.listeners = new Map();
    this.scrollTop = 0;
    this.clientHeight = 400;
    this.scrollHeight = 400;
    this.offsetWidth = 120;
    this.offsetHeight = 28;
    this.classList = {
      contains: (name) => this.className.split(/\s+/).includes(name),
      toggle: (name, force) => {
        const items = new Set(this.className.split(/\s+/).filter(Boolean));
        const on = force === undefined ? !items.has(name) : force;
        if (on) items.add(name); else items.delete(name);
        this.className = [...items].join(" ");
        return on;
      },
      add: (...names) => names.forEach((name) => this.classList.toggle(name, true)),
      remove: (...names) => names.forEach((name) => this.classList.toggle(name, false)),
    };
    this._text = "";
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
  set innerHTML(value) {
    // The unrelated throughput mini-chart writes decorative <i> bars.
    assert.ok(value === "" || /^(<i style="height:[0-9.]+%"><\/i>)+$/.test(value),
      "The mock DOM only supports clearing HTML or decorative mini-chart bars");
    this.children = []; this._text = "";
  }
  get className() { return this.attributes.class || ""; }
  set className(value) { this.attributes.class = value; }
  get childElementCount() { return this.children.length; }
  get firstChild() { return this.children[0]; }
  get lastChild() { return this.children.at(-1); }
  append(...children) {
    for (const child of children) {
      child.parentNode?.removeChild(child);
      child.parentNode = this;
      this.children.push(child);
    }
  }
  appendChild(child) { this.append(child); return child; }
  removeChild(child) {
    this.children.splice(this.children.indexOf(child), 1);
    child.parentNode = null;
    return child;
  }
  remove() { this.parentNode?.removeChild(this); }
  replaceChildren(...children) { this.innerHTML = ""; this.append(...children); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }
  dispatchEvent(event) {
    for (const listener of this.listeners.get(event.type) || []) listener(event);
    return true;
  }
  getBoundingClientRect() { return { width: 1000, height: 700, left: 0, top: 0 }; }
  getTotalLength() { return 100; }
  getPointAtLength(distance) { return { x: distance, y: 0 }; }
  querySelectorAll(selector) {
    const matches = (child) => selector.startsWith(".")
      ? child.classList.contains(selector.slice(1))
      : child.tagName === selector;
    return this.children.flatMap((child) => [
      ...(matches(child) ? [child] : []), ...child.querySelectorAll(selector),
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

const html = fs.readFileSync(process.argv[2], "utf8");
const inline = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
for (const match of html.matchAll(/\bid="([^"]+)"/g)) elements.set(match[1], new Element());
const element = (id) => {
  assert.ok(elements.has(id), `Missing HTML element: ${id}`);
  return elements.get(id);
};
let now = 110_000;
let socket;
const intervals = [];
const frames = [];
class Clock extends Date {
  static now() { return now; }
}
const context = vm.createContext({
  console, Date: Clock, performance: { now: () => now },
  document: {
    getElementById: element,
    createElement: (tag) => new Element(tag),
    createElementNS: (_, tag) => new Element(tag),
    createTextNode: (text) => { const node = new Element("#text"); node.textContent = text; return node; },
  },
  window: { addEventListener() {}, matchMedia: () => ({ matches: false }) },
  location: { protocol: "http:", host: "localhost:7788" },
  WebSocket: class { constructor() { socket = this; } close() {} },
  requestAnimationFrame: (fn) => frames.push(fn),
  setTimeout() {}, clearTimeout() {},
  setInterval: (fn) => intervals.push(fn),
});
const hooked = inline.replace(/\n\}\)\(\);\s*$/, `
  globalThis.dashboard = { S, handle, hardReset, render };
})();`);
assert.notEqual(hooked, inline, "Unable to expose dashboard closure for testing");
vm.runInContext(hooked, context, { filename: "dashboard.html" });
const app = context.dashboard;
socket.onopen();
const active = () => Object.entries(app.S.status)
  .filter(([, state]) => state.state === "running").map(([id]) => id).sort();
const paint = () => {
  app.render();
  // A real render may schedule flow animations; only execute this frame's jobs.
  for (const frame of frames.splice(0)) frame(now);
};
const event = (type, payload = {}) => app.handle({ type, run_id: "test", ts: now / 1000, ...payload });
const topology = {
  type: "graph.topology", run_id: "test", source: "langgraph", title: "Activity test",
  nodes: [
    { id: "alpha", label: "Alpha", kind: "node", color: "#00c6af" },
    { id: "beta", label: "Beta", kind: "node", color: "#fa9500" },
    { id: "gamma", label: "Gamma", kind: "node", color: "#9500fa" },
  ],
  edges: [{ source: "alpha", target: "beta" }, { source: "beta", target: "gamma" }],
  stages: [
    { index: 1, label: "Alpha stage", nodes: ["alpha"] },
    { index: 2, label: "Beta stage", nodes: ["beta"] },
    { index: 3, label: "Gamma stage", nodes: ["gamma"] },
  ],
  mesh: { positions: {
    alpha: { x: 0, y: 0, r: 50 }, beta: { x: 200, y: 0, r: 50 }, gamma: { x: 400, y: 0, r: 50 },
  } },
};
const start = () => { app.handle(topology); event("run.start", { ts: 100 }); };

// A persisted topology from before display compaction, including boundaries of
// nested subgraphs. A real graph node called "review" must remain visible.
const markerTopology = () => {
  const nodes = [
    ["__start__", "start"], ["alpha", "node"],
    ["writer/__start__", "start"], ["writer/review/__start__", "start"],
    ["review", "node"], ["writer/review/__end__", "end"],
    ["writer/__end__", "end"], ["beta", "node"],
    ["retry/__start__", "start"], ["retry/__end__", "end"], ["__end__", "end"],
  ].map(([id, kind]) => ({ id, kind, label: id, color: "#00c6af" }));
  const edges = [
    { source: "__start__", target: "alpha" },
    { source: "alpha", target: "writer/__start__" },
    { source: "writer/__start__", target: "writer/review/__start__", conditional: true, label: "review needed" },
    { source: "writer/review/__start__", target: "review" },
    { source: "writer/review/__start__", target: "beta", conditional: true, label: "skip" },
    { source: "review", target: "writer/review/__end__" },
    { source: "writer/review/__end__", target: "writer/__end__" },
    { source: "writer/__end__", target: "beta", conditional: true, label: "approved" },
    { source: "beta", target: "retry/__start__" },
    { source: "retry/__start__", target: "retry/__end__" },
    { source: "retry/__end__", target: "beta", conditional: true, label: "retry", back: true },
    { source: "beta", target: "__end__" },
  ];
  const meshPositions = {}, flowPositions = {};
  nodes.forEach((node, index) => {
    const angle = -Math.PI / 2 + 2 * Math.PI * index / nodes.length;
    const r = node.kind === "node" ? 58 : 34;
    meshPositions[node.id] = { x: Math.cos(angle) * 600, y: Math.sin(angle) * 600, r, angle };
    flowPositions[node.id] = { x: 0, y: index * 200, r, layer: index, index: 0 };
  });
  return {
    type: "graph.topology", run_id: "test", source: "langgraph", title: "Nested markers",
    mode: "constellation", nodes, edges,
    stages: nodes.filter((node) => node.kind === "node")
      .map((node, index) => ({ index: index + 1, label: node.label, nodes: [node.id] })),
    mesh: { hub: null, radius: 600, positions: meshPositions },
    layout: { positions: flowPositions, back_edges: [["retry/__end__", "beta"]] },
  };
};
const renderedNodes = () => Object.keys(app.S.nodeEls).sort();
const displayedEdge = (source, target) => app.S.edges.find((edge) => edge.source === source && edge.target === target);

const scenarios = {
  waiting() {
    paint();
    assert.equal(element("activity").dataset.state, "waiting");
    assert.equal(element("activity-nodes").childElementCount, 0);
    assert.match(element("activity-message").textContent, /waiting for a run/i);
    start();
    paint();
    assert.deepEqual(active(), []);
    assert.match(element("activity-message").textContent, /waiting|between/i);
    event("node.start", { node: "alpha" });
    event("node.end", { node: "alpha", ms: 200 });
    paint();
    assert.equal(element("activity-nodes").childElementCount, 0);
    assert.match(element("activity-message").textContent, /waiting|between/i);
  },
  parallel() {
    start();
    event("node.start", { node: "alpha", ts: 103 });
    event("node.start", { node: "beta", ts: 105 });
    paint();
    assert.deepEqual(active(), ["alpha", "beta"]);
    assert.equal(element("activity").dataset.state, "running");
    assert.equal(element("activity-nodes").childElementCount, 2);
    assert.match(element("activity-nodes").textContent, /alpha/i);
    assert.match(element("activity-nodes").textContent, /beta/i);
    assert.ok(app.S.nodeEls.alpha.g.classList.contains("running"));
    assert.ok(app.S.nodeEls.beta.g.classList.contains("running"));
    assert.equal(app.S.nodeEls.alpha.badge.hidden, false);
    assert.equal(app.S.nodeEls.beta.badge.hidden, false);
    assert.equal(app.S.nodeEls.gamma.badge.hidden, true);
    assert.deepEqual(element("stepper").children.map((stage) => stage.classList.contains("on")), [true, true, false]);
    event("node.end", { node: "alpha", ms: 7000 });
    paint();
    assert.deepEqual(active(), ["beta"]);
    assert.equal(element("activity-nodes").childElementCount, 1);
    assert.doesNotMatch(element("activity-nodes").textContent, /alpha/i);
    assert.match(element("activity-nodes").textContent, /beta/i);
    assert.equal(app.S.nodeEls.alpha.badge.hidden, true);
    assert.equal(app.S.nodeEls.beta.badge.hidden, false);
    assert.deepEqual(element("stepper").children.map((stage) => stage.classList.contains("on")), [false, true, false]);
  },
  arrival() {
    start();
    event("node.start", { node: "alpha" });
    paint();
    const node = app.S.nodeEls.alpha.g;
    assert.ok(node.classList.contains("arriving"));
    event("log", { node: "alpha", text: "Model token stream continues" });
    paint();
    assert.ok(node.classList.contains("arriving"), "An unrelated render must not interrupt the arrival pulse");
    node.dispatchEvent({ type: "animationend", animationName: "unrelated" });
    assert.ok(node.classList.contains("arriving"));
    node.dispatchEvent({ type: "animationend", animationName: "arrival" });
    assert.equal(node.classList.contains("arriving"), false);
    paint();
    assert.equal(node.classList.contains("arriving"), false, "A finished arrival pulse must not restart on render");
    event("node.end", { node: "alpha", ms: 100 });
    event("node.start", { node: "alpha" });
    paint();
    assert.ok(node.classList.contains("arriving"), "A new execution gets a fresh arrival pulse");
    event("node.end", { node: "alpha", ms: 100 });
    paint();
    assert.equal(node.classList.contains("arriving"), false, "Completion must immediately clear arrival emphasis");
  },
  overlap() {
    start();
    event("node.start", { node: "alpha", ts: 101 });
    event("node.start", { node: "alpha", ts: 102 });
    event("node.end", { node: "alpha", ts: 105, ms: 4000 });
    paint();
    assert.deepEqual(active(), ["alpha"], "One finishing invocation must not hide another running invocation");
    assert.equal(app.S.status.alpha.startedAt, 102000);
    assert.equal(app.S.status.alpha.activeStarts.length, 1);
    event("node.error", { node: "alpha", error: "failed", ms: 8000 });
    paint();
    assert.deepEqual(active(), []);
    assert.equal(app.S.status.alpha.state, "error");
    event("node.start", { node: "alpha", ts: 110 });
    event("node.start", { node: "alpha", ts: 111 });
    event("node.error", { node: "alpha", ms: 2000 });
    assert.deepEqual(active(), ["alpha"]);
    event("node.end", { node: "alpha", ms: 1000 });
    assert.equal(app.S.status.alpha.state, "error", "A successful sibling must not hide this batch's error");
    event("node.start", { node: "alpha" });
    event("node.end", { node: "alpha", ms: 100 });
    assert.equal(app.S.status.alpha.state, "done", "A new batch must not inherit an old error");
  },
  completion() {
    start();
    event("node.start", { node: "alpha" });
    event("node.start", { node: "beta" });
    event("node.end", { node: "beta", ms: 100 });
    event("edge.traverse", { source: "alpha", target: "beta" });
    event("run.end", { status: "error" });
    paint();
    assert.deepEqual(active(), []);
    assert.equal(app.S.status.alpha.state, "stopped", "An interrupted node was never confirmed done");
    assert.equal(app.S.status.beta.state, "done");
    assert.equal(app.S.status.alpha.activeStarts.length, 0);
    assert.equal(app.S.status.alpha.startedAt, null);
    assert.equal(app.S.lastHandoff, null);
    assert.equal(element("activity-nodes").childElementCount, 0);
    assert.equal(element("activity").dataset.state, "error");
    assert.ok(element("stepper").children.every((stage) => !stage.classList.contains("on")));
    assert.ok(Object.values(app.S.nodeEls).every((refs) => refs.badge.hidden && !refs.g.classList.contains("running")));
    event("node.start", { node: "gamma" });
    event("edge.traverse", { source: "beta", target: "gamma" });
    paint();
    assert.deepEqual(active(), [], "Late events cannot reactivate a completed run");
    assert.equal(app.S.lastHandoff, null);
  },
  replay() {
    const events = [
      { ...topology, seq: 1 },
      { type: "run.start", run_id: "test", ts: 100, seq: 2 },
      { type: "node.start", run_id: "test", node: "alpha", ts: 105, seq: 3 },
    ];
    socket.onmessage({ data: JSON.stringify({ type: "replay", events }) });
    paint();
    assert.equal(app.S.status.alpha.startedAt, 105000);
    assert.match(element("activity-nodes").textContent, /5(?:\.0)?s/);
    assert.equal(app.S.nodeEls.alpha.g.classList.contains("arriving"), false, "Replay must not pulse historical arrivals");
    now = 115000;
    for (const tick of intervals) tick();
    assert.match(element("activity-nodes").textContent, /10(?:\.0)?s/, "The NOW timer must advance without incoming events");
    const announcement = element("activity-announcement").textContent;
    now = 116000;
    for (const tick of intervals) tick();
    assert.equal(element("activity-announcement").textContent, announcement, "Clock ticks must not repeatedly announce the active node");
    socket.onclose();
    paint();
    for (const tick of intervals) tick();
    assert.equal(element("activity").dataset.state, "offline");
    assert.match(app.S.nodeEls.alpha.badge.textContent, /last seen here/i);
    const frozen = element("activity-nodes").textContent;
    now = 125000;
    for (const tick of intervals) tick();
    assert.equal(element("activity-nodes").textContent, frozen, "Disconnected activity must not imply continued observed execution");
    for (const timestamp of [128000, 135000]) {
      now = timestamp;
      socket.onclose();
      paint();
      for (const tick of intervals) tick();
      assert.equal(element("activity-nodes").textContent, frozen, "Failed reconnect attempts must preserve the first disconnect's frozen timer");
    }
    socket.onopen();
    paint();
    assert.match(element("activity-nodes").textContent, /30s/, "A successful reconnect resumes the event-based timer");
    socket.onmessage({ data: JSON.stringify({ type: "replay", events: [
      ...events,
      { type: "node.end", run_id: "test", node: "alpha", ts: 107, ms: 2000, seq: 4 },
      { type: "run.end", run_id: "test", ts: 108, status: "ok", seq: 5 },
    ] }) });
    paint();
    assert.deepEqual(active(), []);
    assert.equal(element("activity-nodes").childElementCount, 0);
    assert.notEqual(element("activity").dataset.state, "running");
    assert.equal(app.S.lastHandoff, null);
  },
  handoff() {
    start();
    event("edge.traverse", { source: "alpha", target: "beta", ts: 106 });
    event("node.start", { node: "beta", ts: 107 });
    paint();
    assert.equal(app.S.lastHandoff.key, "alpha→beta");
    assert.match(element("activity-handoff").textContent, /alpha.*beta/i);
    assert.ok(app.S.linkIndex["alpha→beta"].classList.contains("recent"));
    assert.equal(app.S.handoffArrow.getAttribute("visibility"), "visible");
    event("node.end", { node: "beta", ms: 3000 });
    paint();
    assert.equal(app.S.lastHandoff.key, "alpha→beta", "Handoff context persists while waiting for the next node");
    event("edge.traverse", { source: "alpha", target: "gamma" });
    paint();
    assert.equal(app.S.lastHandoff.key, "alpha→gamma", "Dynamically declared valid edges can be the latest handoff");
    assert.ok(app.S.linkIndex["alpha→gamma"]);
    assert.ok(app.S.linkIndex["alpha→gamma"].classList.contains("recent"));
    assert.equal(app.S.linkIndex["alpha→beta"].classList.contains("recent"), false);
    event("run.end", { status: "ok" });
    paint();
    assert.equal(app.S.lastHandoff, null);
    assert.ok(element("activity-handoff").hidden);
    assert.equal(app.S.handoffArrow.getAttribute("visibility"), "hidden");
    event("run.start", { run_id: "next" });
    paint();
    assert.equal(app.S.lastHandoff, null);
    assert.deepEqual(active(), []);
    app.hardReset();
    paint();
    assert.equal(app.S.lastHandoff, null);
    assert.equal(element("activity-nodes").childElementCount, 0);
  },
  isolation() {
    start();
    event("node.start", { node: "alpha", seq: 10 });
    event("node.start", { node: "alpha", seq: 10 });
    assert.equal(app.S.status.alpha.activeStarts.length, 1, "Repeated delivery of the same event is not another invocation");
    event("node.start", { node: "beta", run_id: "nested", seq: 11 });
    event("edge.traverse", { source: "alpha", target: "beta", run_id: "nested", seq: 12 });
    event("run.end", { run_id: "nested", status: "ok", seq: 13 });
    paint();
    assert.deepEqual(active(), ["alpha"]);
    assert.equal(app.S.endedAt, null);
    assert.equal(app.S.lastHandoff, null);
    assert.equal(element("activity-nodes").childElementCount, 1);
    assert.doesNotMatch(element("activity-nodes").textContent, /beta/i);
  },
  nested() {
    start();
    event("iter.start", { iteration: 1 });
    event("node.start", { node: "alpha", iteration: 1 });
    event("node.end", { node: "alpha", iteration: 1, ms: 12 });
    event("node.start", { node: "beta", iteration: 1 });
    const expanded = structuredCloneForTest(topology);
    expanded.nodes = expanded.nodes.filter((node) => node.id !== "beta");
    expanded.nodes.push({ id: "beta/work", label: "Work", kind: "node", color: "#fa9500" });
    expanded.edges = [{ source: "alpha", target: "beta/work" }, { source: "beta/work", target: "gamma" }];
    expanded.mesh.positions["beta/work"] = expanded.mesh.positions.beta;
    delete expanded.mesh.positions.beta;
    app.handle(expanded);
    event("node.start", { node: "beta/work", iteration: 1 });
    event("metric", { name: "tokens", node: "beta/work", input: 10, output: 20, total: 30 });
    paint();
    assert.deepEqual(active(), ["beta/work"]);
    assert.equal(app.S.status.beta, undefined, "Replaced wrapper must not remain active or count twice");
    assert.equal(app.S.status.alpha.hits, 1, "Expanding topology must preserve prior work");
    assert.equal(app.S.tokens, 30);
    assert.equal(app.S.runId, "test");
    event("node.end", { node: "beta/work", iteration: 1, ms: 40 });
    event("run.end", { status: "partial" });
    paint();
    assert.deepEqual(active(), []);
  },
  compact_nodes() {
    const graph = markerTopology();
    const original = JSON.stringify(graph);
    app.handle(graph);
    paint();
    assert.deepEqual(renderedNodes(), ["alpha", "beta", "review"]);
    assert.equal(element("mesh").querySelectorAll(".node").length, 3,
      "Only executable graph nodes should produce circles");
    assert.ok(app.S.nodeEls.review.pill, "A real node named review is not a boundary marker");
    assert.deepEqual(Object.keys(app.S.positions).sort(), ["alpha", "beta", "review"]);
    const nodeIds = new Set(renderedNodes());
    assert.ok(app.S.edges.every((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)));
    assert.equal(app.S.edges.length, 4, "Chains should collapse to work-to-work edges without duplicates");
    for (const [source, target, label] of [
      ["alpha", "review", "review needed"], ["alpha", "beta", "skip"],
      ["review", "beta", "approved"], ["beta", "beta", "retry"],
    ]) {
      const edge = displayedEdge(source, target);
      assert.ok(edge, `Missing compact edge ${source}→${target}`);
      assert.equal(edge.conditional, true);
      assert.ok(edge.label.includes(label), `Missing branch label ${label}`);
      assert.ok(app.S.linkIndex[`${source}→${target}`], "Compacted edges must actually render");
    }
    assert.ok(app.S.radius < graph.mesh.radius, "Boundary markers must no longer inflate the orbit radius");
    assert.equal(JSON.stringify(graph), original, "Compacting the display must preserve the raw event for replay");

    const flowGraph = structuredCloneForTest(graph);
    flowGraph.mode = "flowchart";
    app.handle(flowGraph);
    paint();
    assert.deepEqual(renderedNodes(), ["alpha", "beta", "review"]);
    const rawGap = flowGraph.layout.positions.review.y - flowGraph.layout.positions.alpha.y;
    const compactGap = app.S.positions.review.y - app.S.positions.alpha.y;
    assert.ok(compactGap > 0 && compactGap < rawGap,
      "Removing marker rows must close the corresponding gaps in the flowchart");
    assert.ok(app.S.positions.beta.y > app.S.positions.review.y);
  },
  marker_handoff() {
    app.handle(markerTopology());
    event("run.start", { ts: 100 });
    event("edge.traverse", { source: "writer/review/__start__", target: "review" });
    assert.equal(app.S.lastHandoff, null, "An unobserved predecessor must not become a reported handoff");
    event("edge.traverse", { source: "alpha", target: "writer/__start__" });
    paint();
    assert.equal(app.S.lastHandoff, null, "Entering a marker does not predict which branch will execute");
    event("edge.traverse", { source: "writer/__start__", target: "writer/review/__start__" });
    assert.equal(app.S.lastHandoff, null);
    event("edge.traverse", { source: "writer/review/__start__", target: "review" });
    event("node.start", { node: "review" });
    paint();
    assert.equal(app.S.lastHandoff.key, "alpha→review");
    assert.match(element("activity-handoff").textContent, /alpha.*review/i);
    assert.ok(app.S.linkIndex["alpha→review"].classList.contains("recent"));
    assert.equal(app.S.linkIndex["alpha→beta"].classList.contains("recent"), false);
    assert.ok(app.S.nodeEls.review.g.classList.contains("running"));

    event("node.end", { node: "review", ms: 50 });
    event("edge.traverse", { source: "review", target: "writer/review/__end__" });
    event("edge.traverse", { source: "writer/review/__end__", target: "writer/__end__" });
    assert.equal(app.S.lastHandoff.key, "alpha→review", "Partial marker chains retain the last observed visible hop");
    event("edge.traverse", { source: "writer/__end__", target: "beta" });
    paint();
    assert.equal(app.S.lastHandoff.key, "review→beta");
    assert.ok(app.S.linkIndex["review→beta"].classList.contains("recent"));
    event("edge.traverse", { source: "beta", target: "__end__" });
    assert.equal(app.S.lastHandoff.key, "review→beta", "A run boundary is never an activity destination");

    event("edge.traverse", { source: "alpha", target: "writer/__start__" });
    event("edge.traverse", { source: "writer/__start__", target: "writer/review/__start__" });
    event("edge.traverse", { source: "writer/review/__start__", target: "beta" });
    assert.equal(app.S.lastHandoff.key, "alpha→beta", "Only the branch actually observed is highlighted");
    event("edge.traverse", { source: "beta", target: "review" });
    paint();
    assert.equal(app.S.lastHandoff.key, "beta→review", "Direct dynamic work-node hops remain supported");
    assert.ok(app.S.linkIndex["beta→review"].classList.contains("recent"));
    assert.deepEqual(renderedNodes(), ["alpha", "beta", "review"]);
  },
  marker_replay() {
    const events = [
      { ...markerTopology(), seq: 1 },
      { type: "run.start", run_id: "test", ts: 100, seq: 2 },
      { type: "edge.traverse", run_id: "test", source: "alpha", target: "writer/__start__", ts: 101, seq: 3 },
      { type: "edge.traverse", run_id: "test", source: "writer/__start__", target: "writer/review/__start__", ts: 102, seq: 4 },
    ];
    socket.onmessage({ data: JSON.stringify({ type: "replay", events }) });
    paint();
    assert.deepEqual(renderedNodes(), ["alpha", "beta", "review"]);
    assert.equal(app.S.lastHandoff, null);
    event("edge.traverse", { source: "writer/review/__start__", target: "review", seq: 5 });
    paint();
    assert.equal(app.S.lastHandoff.key, "alpha→review", "A live hop can finish a marker chain restored from old replay data");
    event("run.end", { status: "ok", seq: 6 });
    const next = markerTopology();
    next.run_id = "next";
    app.handle(next);
    event("run.start", { run_id: "next", seq: 7 });
    event("edge.traverse", { run_id: "next", source: "writer/review/__start__", target: "review", seq: 8 });
    paint();
    assert.equal(app.S.lastHandoff, null, "Marker ancestry must not leak into the next run");
  },
  marker_state_reset() {
    app.handle(markerTopology());
    event("run.start", { ts: 100 });
    event("iter.start", { iteration: 1 });
    for (const node of ["__start__", "writer/review/__start__", "writer/__end__", "__end__"]) {
      event("node.start", { node });
      event("state.delta", { node, keys: ["result"] });
      event("log", { node, text: "Marker event from an older producer" });
      event("node.end", { node, ms: 1 });
    }
    paint();
    assert.deepEqual([...app.S.order].sort(), ["alpha", "beta", "review"],
      "Historical marker activity must not recreate removed agent rows");
    assert.deepEqual(renderedNodes(), ["alpha", "beta", "review"]);
    assert.deepEqual(active(), []);

    event("edge.traverse", { source: "alpha", target: "writer/__start__" });
    event("edge.traverse", { source: "writer/__start__", target: "writer/review/__start__" });
    event("iter.end", { iteration: 1, status: "ok" });
    event("iter.start", { iteration: 2 });
    event("edge.traverse", { source: "writer/review/__start__", target: "review" });
    assert.equal(app.S.lastHandoff, null, "Marker ancestry must not leak into the next iteration");
    event("edge.traverse", { source: "alpha", target: "writer/__start__" });
    app.hardReset();
    app.handle(markerTopology());
    event("run.start", { ts: 110 });
    event("edge.traverse", { source: "writer/__start__", target: "writer/review/__start__" });
    event("edge.traverse", { source: "writer/review/__start__", target: "review" });
    paint();
    assert.equal(app.S.lastHandoff, null, "A replay reset must also clear pending marker ancestry");
  },
  compact_update() {
    start();
    event("node.start", { node: "alpha" });
    event("node.end", { node: "alpha", ms: 20 });
    event("node.start", { node: "gamma" });
    app.handle(markerTopology());
    paint();
    assert.deepEqual(renderedNodes(), ["alpha", "beta", "review"]);
    assert.equal(app.S.status.alpha.hits, 1, "A display refresh must preserve completed graph work");
    assert.equal(app.S.status.gamma, undefined, "A replaced wrapper must no longer be active");
    assert.deepEqual(active(), []);
    event("node.start", { node: "review" });
    event("edge.traverse", { source: "alpha", target: "writer/__start__" });
    // Nested topology can be republished while a marker chain is in flight.
    app.handle(markerTopology());
    event("edge.traverse", { source: "writer/__start__", target: "writer/review/__start__" });
    event("edge.traverse", { source: "writer/review/__start__", target: "review" });
    paint();
    assert.deepEqual(active(), ["review"]);
    assert.equal(app.S.lastHandoff.key, "alpha→review");
    assert.equal(element("activity-nodes").childElementCount, 1);
    assert.equal(app.S.status.alpha.hits, 1);
  },
  navigation() {
    start();
    paint();
    const mesh = element("mesh"), fit = mesh.getAttribute("viewBox");
    const scale = () => {
      const view = mesh.getAttribute("viewBox").split(/\s+/).map(Number);
      return Math.min(1000 / view[2], 700 / view[3]);
    };
    const originalScale = scale();
    element("graph-zoom-in").dispatchEvent({ type: "click" });
    assert.ok(scale() > originalScale, "Zoom in makes nodes larger");
    element("graph-fit").dispatchEvent({ type: "click" });
    assert.equal(mesh.getAttribute("viewBox"), fit);
    event("node.start", { node: "gamma" });
    element("graph-focus").dispatchEvent({ type: "click" });
    const focused = mesh.getAttribute("viewBox").split(/\s+/).map(Number);
    assert.equal(focused[0] + focused[2] / 2, app.S.positions.gamma.x * app.S.stretch);
    assert.ok(scale() >= 0.89, "Focused nodes are readable independent of graph size");
    let prevented = false;
    mesh.dispatchEvent({ type: "keydown", key: "ArrowDown", preventDefault() { prevented = true; } });
    assert.ok(prevented);
    assert.ok(Number(mesh.getAttribute("viewBox").split(/\s+/)[1]) > focused[1]);
    event("run.end", { status: "ok" });
    event("run.start", { run_id: "next" });
    assert.equal(app.S.camera, null, "A new run resets the previous graph camera");
  },
};
function structuredCloneForTest(value) { return JSON.parse(JSON.stringify(value)); }
const scenario = process.argv[3];
assert.ok(scenarios[scenario], `Unknown scenario: ${scenario}`);
scenarios[scenario]();
