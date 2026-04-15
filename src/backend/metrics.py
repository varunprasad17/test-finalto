"""
metrics.py — Pure functions that derive dashboard metrics from AppState.

Kept separate from state.py so that calculation logic is easy to read and test
without needing to construct a full AppState.
"""

import time
from typing import Any

from state import AppState


def record_pnl_snapshot(state: AppState) -> None:
    """Append a timestamped total-PnL data point to the history ring buffer."""
    state.pnl_history.append(
        {
            "ts": time.time(),
            "total_pnl": state.get_total_pnl(),
        }
    )


def apply_price_event(state: AppState, event: dict[str, Any]) -> None:
    """
    Update instrument prices and record a price-history data point.

    Called on every 'price' event from the streamer.
    """
    instrument = event["instrument"]
    pos = state.get_or_create_position(instrument)
    pos.bid = event["bid"]
    pos.ask = event["ask"]
    pos.mid = event["mid"]

    # Keep a rolling price history for sparklines / price charts
    if instrument not in state.price_history:
        state.price_history[instrument] = __import__("collections").deque(maxlen=3600)
    state.price_history[instrument].append({"ts": event["ts"], "mid": event["mid"]})

    # Snapshot PnL after every price update so the curve stays smooth
    record_pnl_snapshot(state)


def apply_trade_event(state: AppState, event: dict[str, Any]) -> None:
    """
    Update book position and client stats after a client trade.

    Called on every 'trade' event from the streamer.
    """
    instrument = event["instrument"]
    client_id = event["client_id"]
    side = event["side"]
    qty = event["qty"]
    price = event["price"]

    pos = state.get_or_create_position(instrument)
    mid = pos.mid if pos.mid else price  # fall back to trade price if no mid yet
    pos.apply_trade(side, qty, price)

    client = state.get_or_create_client(client_id)
    client.apply_trade(side, qty, price, mid)

    state.recent_trades.appendleft(
        {
            "ts": event["ts"],
            "client_id": client_id,
            "instrument": instrument,
            "side": side,
            "qty": qty,
            "price": price,
        }
    )


def build_live_update(state: AppState) -> dict[str, Any]:
    """
    Build a compact update payload to broadcast to dashboard subscribers.

    Intentionally lighter than the full snapshot — only fields that change
    frequently are included so the WebSocket payload stays small.
    """
    return {
        "type": "update",
        "total_pnl": state.get_total_pnl(),
        "positions": {k: v.to_dict() for k, v in state.positions.items()},
        "clients": {k: v.to_dict() for k, v in state.clients.items()},
        "latest_trade": state.recent_trades[0] if state.recent_trades else None,
        "pnl_snapshot": state.pnl_history[-1] if state.pnl_history else None,
        "price_tick": {k: list(v)[-1] for k, v in state.price_history.items() if v},
    }
