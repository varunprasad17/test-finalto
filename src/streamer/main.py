"""
Streamer Service
================
Generates mock price ticks and client trades for 3 instruments, then broadcasts
them as JSON events over a WebSocket server.

Instruments: BTC/USD, GOLD/USD, MSFT/USD
Tick rate  : 1 event per second (configurable via TICK_RATE_HZ env var)
Clients    : 5 mock clients with independent random trading activity

Event types
-----------
Price tick::

    {"type": "price", "instrument": "BTC/USD",
     "bid": 68100.50, "ask": 68105.50, "mid": 68103.00, "ts": 1712345678.123}

Trade::

    {"type": "trade", "client_id": "client_2", "instrument": "BTC/USD",
     "side": "BUY", "qty": 0.5, "price": 68105.50, "ts": 1712345678.456}

Book convention (Finalto's view)
---------------------------------
- Client BUY  → client buys at ask  → Finalto is SHORT that qty
- Client SELL → client sells at bid → Finalto is LONG that qty
"""

import asyncio
from dataclasses import dataclass
import json
import logging
import os
import random
import time
from typing import Any

import websockets
from websockets.server import ServerConnection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [streamer] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TICK_RATE_HZ: float = float(os.getenv("TICK_RATE_HZ", "1"))  # ticks/second
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8001"))


NUM_CLIENTS: int = int(os.getenv("NUM_CLIENTS", "5"))
# Probability that a given client trades on any given tick (per instrument)
TRADE_PROBABILITY: float = float(os.getenv("TRADE_PROBABILITY", "0.15"))


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class InstrumentState:
    name: str
    mid: float
    half_spread: float
    volatility: float  # std dev of single-step price move
    min_qty: float
    max_qty: float

    @property
    def bid(self) -> float:
        return round(self.mid - self.half_spread, 5)

    @property
    def ask(self) -> float:
        return round(self.mid + self.half_spread, 5)

    def step(self) -> None:
        """Advance mid price by one GBM-like random step."""
        move = random.gauss(0, self.volatility / (TICK_RATE_HZ**0.5))
        self.mid = max(self.mid + move, self.half_spread * 2)  # floor at 0
        self.mid = round(self.mid, 5)

    def random_qty(self) -> float:
        qty = random.uniform(self.min_qty, self.max_qty)
        # Round to 2 decimal places so qty looks realistic
        return round(qty, 2)


def build_instruments() -> dict[str, InstrumentState]:
    instruments: dict[str, dict[str, Any]] = {
        "BTC/USD": {
            "mid": 68_000.0,
            "half_spread": 5.0,
            "volatility": 150.0,
            "min_qty": 0.01,
            "max_qty": 1.0,
        },
        "GOLD/USD": {
            "mid": 2_300.0,
            "half_spread": 0.50,
            "volatility": 5.0,
            "min_qty": 0.1,
            "max_qty": 10.0,
        },
        "MSFT/USD": {
            "mid": 420.0,
            "half_spread": 0.05,
            "volatility": 1.5,
            "min_qty": 1,
            "max_qty": 50,
        },
    }
    return {name: InstrumentState(name=name, **cfg) for name, cfg in instruments.items()}


CLIENT_IDS: list[str] = [f"client_{i}" for i in range(1, NUM_CLIENTS + 1)]

# Shared set of connected WebSocket clients
_connected: set[ServerConnection] = set()


# ---------------------------------------------------------------------------
# WebSocket handlers
# ---------------------------------------------------------------------------


async def handler(ws: ServerConnection) -> None:
    """Accept a new subscriber and keep the connection alive."""
    _connected.add(ws)
    log.info("Client connected: %s  (total: %d)", ws.remote_address, len(_connected))
    try:
        await ws.wait_closed()
    finally:
        _connected.discard(ws)
        log.info("Client disconnected: %s  (total: %d)", ws.remote_address, len(_connected))


async def broadcast(message: str) -> None:
    """Send a message to all connected subscribers."""
    if not _connected:
        return
    # websockets.broadcast is fire-and-forget; errors are logged by the library
    websockets.broadcast(_connected, message)


# ---------------------------------------------------------------------------
# Event generators
# ---------------------------------------------------------------------------


def make_price_event(inst: InstrumentState) -> str:
    return json.dumps(
        {
            "type": "price",
            "instrument": inst.name,
            "bid": inst.bid,
            "ask": inst.ask,
            "mid": round(inst.mid, 5),
            "ts": time.time(),
        }
    )


def make_trade_event(inst: InstrumentState, client_id: str) -> str:
    side = random.choice(["BUY", "SELL"])
    price = inst.ask if side == "BUY" else inst.bid
    return json.dumps(
        {
            "type": "trade",
            "client_id": client_id,
            "instrument": inst.name,
            "side": side,
            "qty": inst.random_qty(),
            "price": price,
            "ts": time.time(),
        }
    )


# ---------------------------------------------------------------------------
# Main tick loop
# ---------------------------------------------------------------------------


async def tick_loop(instruments: dict[str, InstrumentState]) -> None:
    """
    Every 1/TICK_RATE_HZ seconds:
    1. Advance each instrument's price.
    2. Broadcast a price event for each instrument.
    3. Randomly simulate client trades.
    """
    interval = 1.0 / TICK_RATE_HZ
    log.info(
        "Tick loop started — %s instruments, %.1f tick/s, %d clients, trade prob %.0f%%",
        len(instruments),
        TICK_RATE_HZ,
        NUM_CLIENTS,
        TRADE_PROBABILITY * 100,
    )

    while True:
        tick_start = time.monotonic()

        for inst in instruments.values():
            inst.step()
            price_msg = make_price_event(inst)
            await broadcast(price_msg)
            if _connected:
                log.debug("price  %s bid=%.5f ask=%.5f", inst.name, inst.bid, inst.ask)

            # Each client independently decides whether to trade this tick
            for client_id in CLIENT_IDS:
                if random.random() < TRADE_PROBABILITY:
                    trade_msg = make_trade_event(inst, client_id)
                    await broadcast(trade_msg)
                    payload = json.loads(trade_msg)
                    if _connected:
                        log.info(
                            "trade  %s %s %s qty=%.2f @ %.5f",
                            payload["client_id"],
                            payload["instrument"],
                            payload["side"],
                            payload["qty"],
                            payload["price"],
                        )

        # Sleep for the remainder of the tick interval
        elapsed = time.monotonic() - tick_start
        sleep_for = max(0.0, interval - elapsed)
        await asyncio.sleep(sleep_for)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    instruments = build_instruments()

    log.info("Starting WebSocket server on ws://%s:%d", HOST, PORT)
    async with websockets.serve(handler, HOST, PORT):
        await tick_loop(instruments)


if __name__ == "__main__":
    asyncio.run(main())
