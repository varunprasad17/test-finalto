"""
state.py — In-memory state stores for the backend.

All state lives in a single AppState instance that is created once at startup
and shared across the FastAPI app via dependency injection.

No locking is needed because FastAPI runs on a single-threaded asyncio event
loop — all mutations happen in coroutines that are never concurrent.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Per-instrument position tracking
# ---------------------------------------------------------------------------


@dataclass
class InstrumentPosition:
    """Tracks Finalto's net book position for one instrument."""

    instrument: str

    # Net quantity: positive = long, negative = short
    net_qty: float = 0.0

    # Running total of (price * qty) for long and short legs separately,
    # used to compute a weighted average entry price.
    total_long_cost: float = 0.0
    total_long_qty: float = 0.0
    total_short_cost: float = 0.0
    total_short_qty: float = 0.0

    # Latest market prices (updated on every price tick)
    bid: float = 0.0
    ask: float = 0.0
    mid: float = 0.0

    def apply_trade(self, side: str, qty: float, price: float) -> None:
        """
        Update position after a client trade.

        Client BUY  → Finalto SHORT (net_qty decreases)
        Client SELL → Finalto LONG  (net_qty increases)
        """
        if side == "SELL":
            # Client sells → we go long
            self.net_qty += qty
            self.total_long_cost += price * qty
            self.total_long_qty += qty
        else:
            # Client buys → we go short
            self.net_qty -= qty
            self.total_short_cost += price * qty
            self.total_short_qty += qty

    @property
    def avg_long_entry(self) -> float:
        if self.total_long_qty == 0:
            return 0.0
        return self.total_long_cost / self.total_long_qty

    @property
    def avg_short_entry(self) -> float:
        if self.total_short_qty == 0:
            return 0.0
        return self.total_short_cost / self.total_short_qty

    @property
    def mtm_pnl(self) -> float:
        """
        Mark-to-market PnL using mid price.

        Long leg:  qty X (mid minus avg_entry)
        Short leg: qty X (avg_entry minus mid)   [short profits when price falls]
        """
        long_pnl = (
            self.total_long_qty * (self.mid - self.avg_long_entry) if self.total_long_qty else 0.0
        )
        short_pnl = (
            self.total_short_qty * (self.avg_short_entry - self.mid)
            if self.total_short_qty
            else 0.0
        )
        return round(long_pnl + short_pnl, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument,
            "net_qty": round(self.net_qty, 4),
            "avg_long_entry": round(self.avg_long_entry, 5),
            "avg_short_entry": round(self.avg_short_entry, 5),
            "mtm_pnl": self.mtm_pnl,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
        }


# ---------------------------------------------------------------------------
# Per-client statistics
# ---------------------------------------------------------------------------


@dataclass
class ClientStats:
    """Tracks trading activity and attributed yield per client."""

    client_id: str
    trade_count: int = 0

    # Spread revenue captured on each trade:
    #   Client BUY at ask  → we earn (ask - mid) per unit = half_spread
    #   Client SELL at bid → we earn (mid - bid) per unit = half_spread
    # Summed across all trades this gives total spread income attributed to client.
    spread_captured: float = 0.0

    def apply_trade(self, side: str, qty: float, price: float, mid: float) -> None:
        self.trade_count += 1
        spread = abs(price - mid) * qty
        self.spread_captured += spread

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "trade_count": self.trade_count,
            "spread_captured": round(self.spread_captured, 4),
        }


# ---------------------------------------------------------------------------
# Main application state
# ---------------------------------------------------------------------------


@dataclass
class AppState:
    """
    Single source of truth for all runtime state.

    Instantiated once at startup; mutated only from within the asyncio event
    loop (streamer_client coroutine), so no locking is required.
    """

    # Current book positions per instrument
    positions: dict[str, InstrumentPosition] = field(default_factory=dict)

    # Per-client statistics
    clients: dict[str, ClientStats] = field(default_factory=dict)

    # Ring buffer of recent trades (capped at max_trades)
    recent_trades: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))

    # Ring buffer of timestamped total-PnL snapshots for the PnL curve
    pnl_history: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=500))

    # Ring buffer of price history per instrument { instrument: deque of {ts, mid} }
    price_history: dict[str, deque[dict[str, Any]]] = field(default_factory=dict)

    def get_or_create_position(self, instrument: str) -> InstrumentPosition:
        if instrument not in self.positions:
            self.positions[instrument] = InstrumentPosition(instrument=instrument)
        return self.positions[instrument]

    def get_or_create_client(self, client_id: str) -> ClientStats:
        if client_id not in self.clients:
            self.clients[client_id] = ClientStats(client_id=client_id)
        return self.clients[client_id]

    def get_total_pnl(self) -> float:
        return round(sum(p.mtm_pnl for p in self.positions.values()), 4)

    def snapshot(self) -> dict[str, Any]:
        """Full state snapshot for the REST /api/snapshot endpoint."""
        return {
            "total_pnl": self.get_total_pnl(),
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "clients": {k: v.to_dict() for k, v in self.clients.items()},
            "recent_trades": list(self.recent_trades),
            "pnl_history": list(self.pnl_history),
            "price_history": {k: list(v) for k, v in self.price_history.items()},
        }
