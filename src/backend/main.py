"""
main.py — FastAPI backend for the Finalto Risk Management Dashboard.

Responsibilities
----------------
1. Connect to the streamer WebSocket and maintain in-memory state.
2. Throttle outbound updates to dashboard subscribers at MAX_DASHBOARD_HZ.
3. Expose REST endpoints for initial snapshots and history.
4. Expose a WebSocket endpoint (/ws/live) that the dashboard subscribes to.

Startup sequence
----------------
  asyncio event loop starts
  ├── consume()      — reads from streamer, updates state, sets new_data_event
  └── broadcaster()  — waits on new_data_event, rate-limits, fans out to dashboard clients
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
import json
import logging
import os
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from metrics import build_live_update
from state import AppState
from streamer_client import consume

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [backend] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

MAX_DASHBOARD_HZ: float = float(os.getenv("MAX_DASHBOARD_HZ", "10"))
_MIN_BROADCAST_INTERVAL: float = 1.0 / MAX_DASHBOARD_HZ

# ---------------------------------------------------------------------------
# Shared state & connection registry
# ---------------------------------------------------------------------------

app_state = AppState()
# asyncio.Event — created inside lifespan so it belongs to the running loop
_new_data_event: asyncio.Event | None = None
# Active dashboard WebSocket connections
_dashboard_clients: set[WebSocket] = set()


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------


async def broadcaster() -> None:
    """
    Wait for new data, then fan-out to all connected dashboard clients.

    Enforces MAX_DASHBOARD_HZ by sleeping for the remainder of the minimum
    interval after each broadcast, regardless of how many events arrived.
    """
    log.info("Broadcaster started (max %.0f Hz)", MAX_DASHBOARD_HZ)
    while True:
        if _new_data_event is None:
            await asyncio.sleep(0.05)
            continue
        await _new_data_event.wait()
        _new_data_event.clear()

        if not _dashboard_clients:
            continue

        payload = json.dumps(build_live_update(app_state))
        dead: set[WebSocket] = set()
        for ws in _dashboard_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        _dashboard_clients.difference_update(dead)

        # Rate-limit: sleep until the next broadcast slot
        await asyncio.sleep(_MIN_BROADCAST_INTERVAL)


# ---------------------------------------------------------------------------
# App lifespan — start background tasks
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _new_data_event
    _new_data_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    loop.create_task(consume(app_state, _new_data_event))  # noqa: RUF006
    loop.create_task(broadcaster())  # noqa: RUF006
    log.info("Backend started. Streamer consumer and broadcaster running.")
    yield
    log.info("Backend shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Finalto Risk Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/api/snapshot")  # type: ignore[untyped-decorator]
async def snapshot() -> dict[str, Any]:
    """Full current state — used by the dashboard on initial load."""
    return app_state.snapshot()  # type: ignore[no-any-return]


@app.get("/api/pnl/history")  # type: ignore[untyped-decorator]
async def pnl_history() -> dict[str, Any]:
    """Timestamped total-PnL series for the PnL curve chart."""
    return {"pnl_history": list(app_state.pnl_history)}


@app.get("/api/positions")  # type: ignore[untyped-decorator]
async def positions() -> dict[str, Any]:
    """Current book positions per instrument."""
    return {"positions": {k: v.to_dict() for k, v in app_state.positions.items()}}


@app.get("/api/clients")  # type: ignore[untyped-decorator]
async def clients() -> dict[str, Any]:
    """Per-client trade count and spread captured."""
    return {"clients": {k: v.to_dict() for k, v in app_state.clients.items()}}


@app.get("/api/trades/recent")  # type: ignore[untyped-decorator]
async def recent_trades(limit: int = 50) -> dict[str, Any]:
    """Most recent trades, newest first."""
    return {"trades": list(app_state.recent_trades)[:limit]}


@app.get("/health")  # type: ignore[untyped-decorator]
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WebSocket endpoint — live feed to dashboard
# ---------------------------------------------------------------------------


@app.websocket("/ws/live")  # type: ignore[untyped-decorator]
async def ws_live(ws: WebSocket) -> None:
    """
    Dashboard subscribes here to receive throttled live updates.

    On connect, send the full snapshot immediately so the dashboard doesn't
    start blank while waiting for the first broadcast cycle.
    """
    await ws.accept()
    _dashboard_clients.add(ws)
    log.info("Dashboard client connected (total: %d)", len(_dashboard_clients))

    # Send full snapshot immediately on connect
    with suppress(Exception):
        await ws.send_text(json.dumps({"type": "snapshot", **app_state.snapshot()}))

    try:
        # Keep connection open; the broadcaster handles outbound messages.
        # We still need to receive (and discard) any pings from the client.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _dashboard_clients.discard(ws)
        log.info("Dashboard client disconnected (total: %d)", len(_dashboard_clients))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
