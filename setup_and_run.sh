#!/usr/bin/env bash
# Set up loopscope from a source checkout, run the test suite, and start a
# live dashboard demo.
#
# Usage:
#   ./setup_and_run.sh                 # venv + tests + Ralph demo → :7788
#   ./setup_and_run.sh --langgraph     # cyclic LangGraph demo (installs extra)
#   ./setup_and_run.sh --combo         # Ralph loop driving the graph
#   ./setup_and_run.sh --replay FILE   # play back a JSONL tape
#   ./setup_and_run.sh --setup-only    # venv + deps + tests, no dashboard
#   ./setup_and_run.sh --no-tests      # skip pytest
#   ./setup_and_run.sh --no-browser    # do not open a browser tab
#   ./setup_and_run.sh --port 7788
#   ./setup_and_run.sh --help
#
# Env overrides:
#   LOOPSCOPE_PYTHON       interpreter used to create the venv (>= 3.10)
#   LOOPSCOPE_PORT         dashboard port (default 7788)
#   LOOPSCOPE_NO_BROWSER=1 same as --no-browser
#
# The Ralph demo needs nothing but the three runtime packages. LangGraph is
# an extra, installed only for --langgraph / --combo.
set -euo pipefail

cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

MODE=ralph
SETUP_ONLY=0
RUN_TESTS=1
OPEN_BROWSER=1
PORT="${LOOPSCOPE_PORT:-7788}"
REPLAY_PATH=""
SPEED=4
VENV=.venv

usage() { awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"; }

require_value() {
  if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
    echo "ERROR: $1 needs a value" >&2
    exit 1
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ralph)       MODE=ralph ;;
    --langgraph)
      MODE=langgraph
      if [ "${2:-}" = "ralph" ]; then
        MODE=combo
        shift
      fi
      ;;
    --combo)       MODE=combo ;;
    --replay)
      require_value "$@"
      MODE=replay
      REPLAY_PATH="$2"
      shift
      ;;
    --speed)
      require_value "$@"
      SPEED="$2"
      shift
      ;;
    --port)
      require_value "$@"
      PORT="$2"
      shift
      ;;
    --setup-only)  SETUP_ONLY=1 ;;
    --no-tests)    RUN_TESTS=0 ;;
    --no-browser)  OPEN_BROWSER=0 ;;
    -h|--help)     usage; exit 0 ;;
    *)
      echo "ERROR: unknown option '$1' (try --help)" >&2
      exit 1
      ;;
  esac
  shift
done

[ -n "${LOOPSCOPE_NO_BROWSER:-}" ] && OPEN_BROWSER=0

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "ERROR: --port must be an integer between 1 and 65535" >&2
  exit 1
fi

if [ "$MODE" = "replay" ]; then
  if [ ! -f "$REPLAY_PATH" ]; then
    echo "ERROR: replay file not found: $REPLAY_PATH" >&2
    exit 1
  fi
fi

# ── stale dashboards ────────────────────────────────────────────────────────
# A demo from an earlier run outlives the terminal that started it and keeps
# holding the port, which makes a fresh start look like a hang. Clear ours,
# refuse to fight anyone else's. Only processes whose executable is python
# count, so a shell or editor whose command line merely mentions the file is
# never a kill target.
dashboard_pids() {
  local pid comm
  for pid in $(pgrep -f 'examples/(ralph|langgraph)_demo\.py| -m loopscope\.replay' 2>/dev/null || true); do
    [ "$pid" = "$$" ] && continue
    comm="$(ps -o comm= -p "$pid" 2>/dev/null || true)"
    case "${comm##*/}" in
      python | Python | python[0-9]*) printf '%s\n' "$pid" ;;
    esac
  done
}

stop_stale_dashboards() {
  local pids
  pids="$(dashboard_pids)"
  if [ -n "$pids" ]; then
    echo "==> Stopping stale dashboard process(es): $(echo "$pids" | tr '\n' ' ')"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 2
    pids="$(dashboard_pids)"
    if [ -n "$pids" ]; then
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
      sleep 1
    fi
  fi
  if command -v lsof >/dev/null 2>&1 &&
     lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: port $PORT is held by a process that is not a loopscope dashboard:" >&2
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >&2
    echo "Stop it, or set LOOPSCOPE_PORT / --port to a free port." >&2
    exit 1
  fi
}

# ── interpreter ─────────────────────────────────────────────────────────────
# pyproject requires >= 3.10. Prefer the newest on PATH rather than pinning;
# there is no upper bound. macOS /usr/bin/python3 is often still 3.9 and
# cannot import the package.
pick_python() {
  local candidate
  if [ -n "${LOOPSCOPE_PYTHON:-}" ]; then
    if [ ! -x "${LOOPSCOPE_PYTHON}" ] && ! command -v "${LOOPSCOPE_PYTHON}" >/dev/null 2>&1; then
      echo "ERROR: LOOPSCOPE_PYTHON is not executable: $LOOPSCOPE_PYTHON" >&2
      exit 1
    fi
    if ! "$LOOPSCOPE_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "ERROR: LOOPSCOPE_PYTHON must be Python 3.10 or newer" >&2
      exit 1
    fi
    printf '%s\n' "$LOOPSCOPE_PYTHON"
    return
  fi
  if [ -x "$VENV/bin/python" ] &&
     "$VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    printf '%s\n' "$VENV/bin/python"
    return
  fi
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  echo ""
}

PY="$(pick_python)"
if [ -z "$PY" ]; then
  echo "ERROR: no Python >= 3.10 on PATH. Set LOOPSCOPE_PYTHON." >&2
  exit 1
fi
echo "==> Using $PY ($("$PY" --version 2>&1))"

if [ -x "$VENV/bin/python" ] &&
   ! "$VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "==> Existing $VENV is Python < 3.10 — recreating"
  rm -rf "$VENV"
fi

if [ ! -d "$VENV" ]; then
  echo "==> Creating virtual environment in $VENV"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

EXTRAS="dev"
if [ "$MODE" = "langgraph" ] || [ "$MODE" = "combo" ]; then
  EXTRAS="dev,langgraph"
fi

echo "==> Installing loopscope (extras: $EXTRAS)"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e ".[$EXTRAS]"

# Examples add the repo root to sys.path; PYTHONPATH covers replay and a
# venv whose editable .pth was skipped (seen on some macOS 3.13 layouts).
export PYTHONPATH="${PWD}${PYTHONPATH:+:$PYTHONPATH}"

if [ "$RUN_TESTS" -eq 1 ]; then
  echo "==> Running test suite"
  python -m pytest -q
fi

if [ "$SETUP_ONLY" -eq 1 ]; then
  echo "==> setup-only: dashboard not started"
  exit 0
fi

export LOOPSCOPE_PORT="$PORT"
if [ "$OPEN_BROWSER" -eq 0 ]; then
  export LOOPSCOPE_NO_BROWSER=1
fi

stop_stale_dashboards

echo "==> Dashboard at http://127.0.0.1:$PORT  (Ctrl+C to stop)"
echo "    headless? tunnel with: ssh -L $PORT:127.0.0.1:$PORT <this-host>"

case "$MODE" in
  ralph)
    echo "==> Ralph demo"
    exec python examples/ralph_demo.py
    ;;
  langgraph)
    echo "==> LangGraph demo"
    exec python examples/langgraph_demo.py
    ;;
  combo)
    echo "==> Ralph + LangGraph demo"
    exec python examples/langgraph_demo.py ralph
    ;;
  replay)
    echo "==> Replaying $REPLAY_PATH (speed ${SPEED}x)"
    exec python -m loopscope.replay "$REPLAY_PATH" --port "$PORT" --speed "$SPEED"
    ;;
esac
