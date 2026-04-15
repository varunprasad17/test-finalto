"""
app.py — Streamlit entry point for the Finalto Risk Dashboard.

Responsibilities
----------------
- Page config and global CSS
- Module-level _store + threading.Lock (imported by page modules)
- Background WebSocket thread (writes only to _store, never st.session_state)
- price_ticker fragment (100ms, text only, shown on every page)
- Sidebar navigation → routes to pages/overview, instruments, clients
"""

from collections import deque
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any

import streamlit as st
import websockets.sync.client

# Pages import _store and _lock from this module via sys.path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [dashboard] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BACKEND_WS_URL: str = os.getenv("BACKEND_WS_URL", "ws://localhost:8000/ws/live")

st.set_page_config(
    page_title="Finalto Risk Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Module-level store — written by WS thread, read by page fragments
# ---------------------------------------------------------------------------

_lock = threading.Lock()

_store: dict[str, Any] = {
    "connected": False,
    "total_pnl": 0.0,
    "positions": {},
    "clients": {},
    "recent_trades": deque(maxlen=50),
    "pnl_history": deque(maxlen=500),
    "price_history": {},
}

# ---------------------------------------------------------------------------
# WebSocket background thread
# ---------------------------------------------------------------------------


def _apply_snapshot(data: dict[str, Any]) -> None:
    _store["total_pnl"] = data.get("total_pnl", 0.0)
    _store["positions"] = data.get("positions", {})
    _store["clients"] = data.get("clients", {})
    _store["recent_trades"] = deque(data.get("recent_trades", []), maxlen=50)
    _store["pnl_history"] = deque(data.get("pnl_history", []), maxlen=500)
    _store["price_history"] = {
        k: deque(v, maxlen=3600) for k, v in data.get("price_history", {}).items()
    }


def _apply_update(data: dict[str, Any]) -> None:
    if "total_pnl" in data:
        _store["total_pnl"] = data["total_pnl"]
    if "positions" in data:
        _store["positions"] = data["positions"]
    if "clients" in data:
        _store["clients"] = data["clients"]

    snap = data.get("pnl_snapshot")
    if snap:
        _store["pnl_history"].append(snap)

    price_tick = data.get("price_tick")
    if price_tick:
        for inst, point in price_tick.items():
            if inst not in _store["price_history"]:
                _store["price_history"][inst] = deque(maxlen=3600)
            _store["price_history"][inst].append(point)

    trade = data.get("latest_trade")
    if trade:
        trades: deque[Any] = _store["recent_trades"]
        if not trades or trades[0].get("ts") != trade.get("ts"):
            trades.appendleft(trade)


def _ws_thread() -> None:
    while True:
        try:
            log.info("Connecting to %s …", BACKEND_WS_URL)
            with websockets.sync.client.connect(BACKEND_WS_URL) as ws:
                log.info("Connected to backend.")
                with _lock:
                    _store["connected"] = True
                for raw in ws:
                    data = json.loads(raw)
                    with _lock:
                        if data.get("type") == "snapshot":
                            _apply_snapshot(data)
                        else:
                            _apply_update(data)
        except Exception as exc:
            log.warning("WS disconnected: %s — retry in 2s", exc)
            with _lock:
                _store["connected"] = False
            time.sleep(2)


_thread_started = False
_thread_lock = threading.Lock()


def _ensure_thread() -> None:
    global _thread_started
    with _thread_lock:
        if not _thread_started:
            _thread_started = True
            t = threading.Thread(target=_ws_thread, daemon=True)
            t.start()


_ensure_thread()

# ---------------------------------------------------------------------------
# Imports after sys.path is set so pages can do `from charts import ...`
# ---------------------------------------------------------------------------

from charts import COLORS  # noqa: E402

# ---------------------------------------------------------------------------
# Sidebar — nav + live price ticker
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## Finalto")
    st.divider()
    page = st.radio(
        "Navigate",
        ["Overview", "Instruments", "Clients"],
        label_visibility="collapsed",
    )
    st.divider()

    @st.fragment(run_every="100ms")  # type: ignore[untyped-decorator]
    def price_ticker() -> None:
        with _lock:
            connected = _store["connected"]
            positions = dict(_store["positions"])

        if connected:
            status_html = "<span style='color:#26a69a;font-size:12px'>● LIVE</span>"
        else:
            status_html = "<span style='color:#ef5350;font-size:12px'>● CONNECTING…</span>"

        rows = [status_html, "<br>"]
        for inst, pos in positions.items():
            color = COLORS.get(inst, "#ccc")
            mid = pos.get("mid", 0)
            rows.append(
                f"<div style='margin:6px 0'>"
                f"<span style='color:{color};font-weight:bold;font-size:12px'>{inst}</span><br>"
                f"<span style='font-size:16px;font-weight:bold'>${mid:,.4f}</span>"
                f"</div>"
            )

        st.markdown(
            "<div style='font-family:monospace'>" + "".join(rows) + "</div>",
            unsafe_allow_html=True,
        )

    price_ticker()

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.markdown("## Finalto — Risk Management Dashboard")
st.divider()

# ---------------------------------------------------------------------------
# Route to selected page
# ---------------------------------------------------------------------------

if page == "Overview":
    from views.overview import render
elif page == "Instruments":
    from views.instruments import render
else:
    from views.clients import render

render(_store, _lock)
