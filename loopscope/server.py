"""The dashboard server.

Runs on its own thread with its own event loop so that `start()` returns
immediately and your script keeps its main thread. Every producer therefore
talks to the bus across a thread boundary, which is exactly what the bus is
built for.

Author: Nic Cravino
Email: spidernic@me.com
LinkedIn: https://www.linkedin.com/in/nic-cravino
Created: August 21, 2026
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from .bus import EventBus, default_bus, set_default_bus

STATIC = Path(__file__).parent / "static"


def _origin_allowed(socket: WebSocket) -> bool:
    """Same-origin dashboard, or a loopback client with no Origin (CLI).

    Binding is 127.0.0.1 by default; this is the second door. No auth.
    """
    origin = socket.headers.get("origin")
    host = socket.headers.get("host") or ""
    if origin:
        return origin in (f"http://{host}", f"https://{host}")
    client = socket.client.host if socket.client else ""
    return client in ("127.0.0.1", "::1", "localhost")


def create_app(bus: EventBus) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        bus.bind_loop(asyncio.get_running_loop())
        yield

    app = FastAPI(
        title="loopscope",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "dashboard.html")

    @app.get("/api/replay")
    async def replay() -> JSONResponse:
        return JSONResponse(bus.replay())

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.websocket("/ws")
    async def stream(socket: WebSocket) -> None:
        if not _origin_allowed(socket):
            await socket.close(code=1008)
            return
        await socket.accept()
        # Snapshot + subscribe under one lock in the bus; skip seq already sent.
        queue, snapshot, last_seq = bus.subscribe_and_replay()
        try:
            await socket.send_text(
                json.dumps({"type": "replay", "events": snapshot}, default=str)
            )
            while True:
                event = await queue.get()
                if event.seq <= last_seq:
                    continue
                await socket.send_text(json.dumps(event.as_dict(), default=str))
        except WebSocketDisconnect:
            pass
        except Exception:
            try:
                await socket.close()
            except Exception:
                pass
        finally:
            bus.unsubscribe(queue)

    return app


class Dashboard:
    def __init__(self, bus: EventBus, host: str = "127.0.0.1", port: int = 7788):
        self.bus = bus
        self.host = host
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._server = None

    @property
    def url(self) -> str:
        if self.host in ("0.0.0.0", "::"):
            return f"http://127.0.0.1:{self.port}"
        if self.host == "127.0.0.1":
            return f"http://localhost:{self.port}"
        return f"http://{self.host}:{self.port}"

    def start(self, *, open_browser: bool = False, quiet: bool = True) -> "Dashboard":
        import uvicorn

        config = uvicorn.Config(
            create_app(self.bus),
            host=self.host,
            port=self.port,
            log_level="error" if quiet else "info",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def run() -> None:
            try:
                self._server.run()
            except SystemExit:
                pass

        self._thread = threading.Thread(target=run, name="loopscope", daemon=True)
        self._thread.start()
        try:
            _wait_until_up(self._server, self._thread)
        except RuntimeError:
            self.stop()
            raise RuntimeError(
                f"loopscope could not bind {self.host}:{self.port}"
            ) from None
        if self.host in ("0.0.0.0", "::"):
            print(
                f"loopscope bound on {self.host}:{self.port} — no auth, "
                f"reachable from the network. UI at {self.url}"
            )
        else:
            print(f"loopscope → {self.url}")
        if open_browser:
            try:
                webbrowser.open(self.url)
            except Exception:
                pass
        return self

    def hold(self) -> None:
        """Block so the dashboard outlives a script that has finished.

        Without this, a short run exits and takes the server with it before you
        have read anything.
        """
        print(f"loopscope holding at {self.url} — Ctrl-C to quit")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)


def _wait_until_up(
    server, thread: Optional[threading.Thread] = None, timeout: float = 5.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if getattr(server, "started", False):
            return
        if thread is not None and not thread.is_alive():
            break
        time.sleep(0.05)
    raise RuntimeError("loopscope server failed to start")


def start(
    *,
    host: str = "127.0.0.1",
    port: int = 7788,
    bus: Optional[EventBus] = None,
    open_browser: bool = False,
    jsonl: Optional[str] = None,
) -> Dashboard:
    """Bring up the dashboard and return a handle.

        scope = loopscope.start(open_browser=True)
        ...
        scope.hold()
    """
    if not (1 <= int(port) <= 65535):
        raise ValueError(f"port out of range: {port}")
    if bus is None:
        bus = default_bus()
    if jsonl:
        bus.set_jsonl(jsonl)
    set_default_bus(bus)
    return Dashboard(bus, host=host, port=port).start(open_browser=open_browser)
