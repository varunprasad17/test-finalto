"""
listener.py — Quick CLI listener for the streamer WebSocket feed.

Usage:
    python3 listener.py [ws://localhost:8001]
"""

import asyncio
import json
import sys
from typing import Any

import websockets

URI = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8001"


def fmt_price(d: dict[str, Any]) -> str:
    return (
        f"  PRICE  {d['instrument']:<10}  bid={d['bid']:<14}  ask={d['ask']:<14}  mid={d['mid']}"
    )


def fmt_trade(d: dict[str, Any]) -> str:
    return (
        f"  TRADE  {d['client_id']:<10}  {d['instrument']:<10}  "
        f"{d['side']:<5}  qty={d['qty']:<8}  @ {d['price']}"
    )


async def listen() -> None:
    print(f"Connecting to {URI} ... (Ctrl+C to stop)\n")
    async with websockets.connect(URI) as ws:
        print("Connected.\n")
        async for raw in ws:
            d = json.loads(raw)
            if d["type"] == "price":
                print(fmt_price(d))
            elif d["type"] == "trade":
                print(fmt_trade(d))


if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        print("\nStopped.")
