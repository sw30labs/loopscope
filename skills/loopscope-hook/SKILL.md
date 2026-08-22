---
name: loopscope-hook
description: >
  Wire loopscope into the current project so an existing LangGraph StateGraph
  and/or Ralph loop shows up on a local dashboard. Use when the user is inside
  another repo (VS Code or Grok) and says "hook loopscope", "wire loopscope",
  "watch this graph", "instrument this Ralph loop", "add the loopscope
  dashboard", or runs /loopscope-hook. Do NOT use to rewrite a graph, to design
  a new agent, or when the cwd is the loopscope repo itself (run the demos).
argument-hint: "[path] [langgraph|ralph|both]"
metadata:
  short-description: "Hook loopscope into an existing LangGraph / Ralph project"
  author: "Nic Cravino"
---

# loopscope-hook

You are in **some other project**. loopscope only watches. Do not rewrite the
graph, do not wrap nodes, do not add a database.

This file is the whole skill. Do not fetch docs from the web. Do not require
the loopscope README to be open.

## Invariants

- Python 3.10+ in the **project's** venv.
- Bind `127.0.0.1` only. Never `0.0.0.0`.
- `start()` once per process, before any invoke. Never per request.
- Pass the dict `attach()` / `attach_graph()` returns as `config=`.
- `finish(config)` when that **job** ends. Not between retries of the same job.
- `hold()` only if the process would exit (CLI / notebook). Servers skip it.
- Do not add a machine-local `file://` path to committed lockfiles unless the
  user asks. Install into the venv now; report that.
- Do not hook tests (they would bind the port). Drivers, CLIs, servers, demos.
- Do not launch the dashboard unless the user asks to run it.

## 0. Resolve loopscope (the package to install)

`LOOPSCOPE_HOME` is the checkout that contains `pyproject.toml` and the
`loopscope/` package.

1. `$LOOPSCOPE_HOME` if set and that path has `loopscope/__init__.py`.
2. Real path of **this skill directory** (follow symlinks). If it ends with
   `/skills/loopscope-hook`, the checkout is two directories up. Confirm
   `loopscope/__init__.py` is there.
3. `$HOME/REPOS/loopscope` if that exists.
4. Stop. Ask the user to set `LOOPSCOPE_HOME`.

Target repo = the git root of the current workspace, or the path they passed.

If the target **is** the loopscope checkout: stop. Tell them
`./setup_and_run.sh --langgraph` (or `--combo`). This skill is for other apps.

## 1. Scan the target

Ignore `.venv`, `venv`, `node_modules`, `dist`, `build`, `.git`, `__pycache__`,
`site-packages`.

```bash
rg -n --type py -g '!**/.venv/**' -g '!**/site-packages/**' \
  'StateGraph|langgraph|graph\.compile\(' .
rg -n --type py -g '!**/.venv/**' \
  'RalphLoop|@ralph|loopscope\.(start|attach|ralph)' .
rg -n --type py -g '!**/.venv/**' \
  '\.(invoke|ainvoke|stream|astream)\(' .
```

Classify:

| Finding | Mode |
|---|---|
| `StateGraph` / `graph.compile` and no outer retry loop | `langgraph` |
| Outer loop until a score/count improves, no LangGraph | `ralph` |
| Both (Ralph or `while` around `app.invoke`) | `both` |
| `loopscope.attach` or `attach_graph` already on the live path | **already hooked** — report sites, stop unless they want another |
| None of the above | stop, say so, do not invent a graph |

User flag `langgraph` / `ralph` / `both` overrides the guess. If several
entry points, wire the real driver (CLI `main`, server lifespan, demo). List
the rest. Do not spray `start()` through the tree.

Need compiled graphs: `app = graph.compile()`. Plain LangChain chains will not
light up the mesh.

## 2. Install into the project's interpreter

Prefer the venv they already use (`.venv/bin/python`, `uv run`, poetry env).
Confirm `>= 3.10`. They already have LangGraph if mode is `langgraph`/`both`;
do not install loopscope's `langgraph` extra.

```bash
"$PY" -m pip install -e "$LOOPSCOPE_HOME"
"$PY" -c "import loopscope; print(loopscope.__version__)"
```

`uv`: `uv pip install -e "$LOOPSCOPE_HOME"`.

## 3. Patch — pick one pattern

Keep existing `config` (thread_id, checkpointer, callbacks). `attach()` copies
it and appends its handler.

### A. LangGraph, one job

```python
import loopscope

scope = loopscope.start(open_browser=True)  # process boot, once

config = loopscope.attach(
    app,
    config=existing_config,          # or omit
    title="short name for the run",  # optional
    # roles={"retrieve": "search the doc store"},  # optional subtitles
)
status = "error"
try:
    result = app.invoke(state, config=config)   # or ainvoke / stream / astream
    status = "ok"
finally:
    loopscope.finish(config, status=status)

# CLI only, after the job:
# scope.hold()
```

Server: `start()` in lifespan/startup. `attach`/`finish` around each job.
No `hold()`.

Same job, many invokes (retry / `while`): **one** `attach`, loop `invoke` with
that config, **one** `finish` after the loop. Each invoke is one pass.

New job (new user, new thread, new night) → new `attach()`.

### B. Ralph loop, no graph

```python
import loopscope

scope = loopscope.start(open_browser=True)
loop = loopscope.RalphLoop(
    "get the suite green",
    phases=["plan", "edit", "test"],
    max_iters=20,
    stall_after=5,
)
for it in loop:
    with it.phase("plan") as p:
        p.log("picking the cheapest failures")
    with it.phase("edit"):
        apply_patch()
    with it.phase("test") as p:
        failures = run_tests()
        p.log(f"{failures} failing")
    it.signal(failures, name="failing tests")
    it.note(f"{failures} failing")
    if failures == 0:
        it.done("suite green")
        break
scope.hold()
```

`it.done()` is a flag, not an exception. `break` if you want out of the `for`
now. Do not call `loopscope.finish()` — the loop closes the run.

Decorator form (whole pass in one function; falsy / `0` return converges):

```python
@loopscope.ralph("keep fixing the build", phases=["edit", "test"])
def one_pass(it):
    ...
    return failures
```

Map their existing steps onto `phases=`. Do not invent phases they do not have.
`it.signal` is the number they are driving to zero (failures, distance to 1.0,
open TODOs).

### C. Both — Ralph outside, graph inside

```python
scope = loopscope.start(open_browser=True)
loop = loopscope.RalphLoop("draft until it scores", max_iters=8, stall_after=4)
config = loop.attach_graph(app, config=existing_config)

for it in loop:
    state = app.invoke(state, config=config)
    it.signal(1 - state["score"], name="distance to 1.0")
    it.note(f"score {state['score']}")
    if state["score"] >= 0.9:
        it.done("good enough")
        break
scope.hold()
```

Use `attach_graph`, not `loopscope.attach`. Do not `finish()` — Ralph owns the
run. Put their real score/failure field in `signal`.

### Optional extras (only if they already have the need)

```python
loopscope.start(jsonl="runs/tonight.jsonl", open_browser=True, port=7788)
loopscope.log("retriever returned 0 hits", level="warn")
loopscope.metric("open_todos", 14)
loopscope.attach(app, capture_state=False)  # no state in the browser
```

Replay later: `"$PY" -m loopscope.replay runs/tonight.jsonl --speed 8`

Subtitles: first line of each node function docstring, or `roles={"node": "…"}`.

## 4. Check the patch

- `import loopscope` in the file you touched.
- Exactly one `start()` on the process boot path.
- Every watched `invoke`/`ainvoke`/`stream`/`astream` gets the attach config.
- `finish` in `finally` (mode A) or Ralph closes it (B/C).
- Existing callbacks / `thread_id` still passed through `attach(..., config=)`.
- No `start()` in tests.

Do not run their full suite. A compile check is enough:

```bash
"$PY" -c "import ast, pathlib; ast.parse(pathlib.Path('FILE').read_text())"
```

## 5. Report

- Mode (`langgraph` / `ralph` / `both`)
- `LOOPSCOPE_HOME` used
- Files patched
- How to run **their** entry point (not loopscope's demo)
- Dashboard: http://localhost:7788
- CLI: remind `hold()`. Server: remind start-at-boot.
- Empty dashboard = invoked without the attach config
- Still-running pill = forgot `finish()`
- Bind error = port 7788 taken → `start(port=7799)`

Do not commit unless they ask.
