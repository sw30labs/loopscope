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
};
const scenario = process.argv[3];
assert.ok(scenarios[scenario], `Unknown scenario: ${scenario}`);
scenarios[scenario]();
