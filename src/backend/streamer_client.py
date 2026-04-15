"""
streamer_client.py — Async WebSocket consumer that connects to the streamer
and feeds events into AppState via the metrics helpers.

Rate-limiting
-------------
The streamer may run at any tick rate (e.g. 60 Hz).  This module processes
every event so internal state is always current, but signals the dashboard
broadcaster at most MAX_DASHBOARD_HZ times per second.  A simple asyncio.Event
is used as a "new data available" flag; the broadcaster waits on it and resets
it after each broadcast.
"""

import asyncio
import json
import logging
import os

from metrics import apply_price_event, apply_trade_event
from state import AppState
import websockets

log = logging.getLogger(__name__)

STREAMER_WS_URL: str = os.getenv("STREAMER_WS_URL", "ws://localhost:8001")
RECONNECT_DELAY: float = 3.0  # seconds to wait before reconnecting on error


async def consume(state: AppState, new_data_event: asyncio.Event) -> None:
    """
    Connect to the streamer and process events indefinitely.

    Reconnects automatically if the connection drops.
    """
    while True:
        try:
            log.info("Connecting to streamer at %s ...", STREAMER_WS_URL)
            async with websockets.connect(STREAMER_WS_URL) as ws:
                log.info("Connected to streamer.")
                async for raw in ws:
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        log.warning("Received non-JSON message, skipping.")
                        continue

                    if event.get("type") == "price":
                        apply_price_event(state, event)
                    elif event.get("type") == "trade":
                        apply_trade_event(state, event)
                    else:
                        log.debug("Unknown event type: %s", event.get("type"))

                    # Signal that fresh data is available for the broadcaster
                    new_data_event.set()

        except (websockets.ConnectionClosed, OSError) as exc:
            log.warning(
                "Streamer connection lost (%s). Reconnecting in %.0fs …", exc, RECONNECT_DELAY
            )
            await asyncio.sleep(RECONNECT_DELAY)
        except Exception as exc:
            log.error("Unexpected error in streamer consumer: %s", exc, exc_info=True)
            await asyncio.sleep(RECONNECT_DELAY)
