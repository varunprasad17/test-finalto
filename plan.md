# Risk Management Dashboard — Implementation Plan

## Overview

Three services, all wired together via Docker Compose:

| Service | Tech | Role |
|---|---|---|
| `streamer` | Pure Python + WebSockets | Generates mock prices & trades, streams events |
| `backend` | FastAPI (async) | Aggregates state, exposes REST + WebSocket API |
| `dashboard` | Streamlit | Real-time display of all risk metrics |

---

## Architecture Diagram

```
┌──────────────┐        WebSocket (JSON)        ┌──────────────────┐
│   Streamer   │ ──────────────────────────────► │  FastAPI Backend  │
│  (Port 8001) │                                 │   (Port 8000)     │
└──────────────┘                                 └────────┬─────────┘
                                                          │ WebSocket / REST
                                                          ▼
                                                 ┌──────────────────┐
                                                 │  Streamlit UI     │
                                                 │  (Port 8501)      │
                                                 └──────────────────┘
```

---

## Service 1 — Streamer (`src/streamer/`)

**Purpose:** Generate realistic-ish mock market data and client trading activity, and broadcast it.

### Instruments (hardcoded, 3)
```
BTC/USD, GOLD/USD, MSFT/USD
```

### Price Generation
- Each instrument runs an independent **geometric Brownian motion** random walk.
- Every tick: mid price moves by a small random step; spread is fixed per instrument.
- Publishes `bid`, `ask`, `mid`, `timestamp`, `instrument`.
- Tick rate: **1 tick/second per instrument** (configurable via `TICK_RATE_HZ` env var; docker-compose default is 10).

### Client Trading Simulation
- 5 mock clients, each trading independently with configurable probability per tick (`TRADE_PROBABILITY`, default 0.15).
- On each tick, each client independently decides whether to trade (buy or sell), and what size.
- Trade: `client_id`, `instrument`, `side` (`BUY`/`SELL`), `qty`, `price`, `ts`.

### Book Impact (Finalto's side)
- Client **buys** → Finalto is **short** that quantity.
- Client **sells** → Finalto is **long** that quantity.

### Output
- WebSocket server on `ws://streamer:8001`.
- Sends a mixed stream of two event types:
  ```json
  { "type": "price", "instrument": "BTC/USD", "bid": 68100.50, "ask": 68110.50, "mid": 68105.00, "ts": 1712345678.123 }
  { "type": "trade", "client_id": "client_3", "instrument": "BTC/USD", "side": "BUY", "qty": 0.5, "price": 68110.50, "ts": 1712345678.456 }
  ```

---

## Service 2 — Backend (`src/backend/`)

**Purpose:** Stateful aggregation layer. Consumes the streamer, maintains positions/PnL, exposes data to the dashboard.

### State Maintained (in-memory, Python dicts)
| Store | Description |
|---|---|
| `latest_prices` | Last bid/ask/mid per instrument |
| `positions` | Net position per instrument (Finalto book) |
| `client_positions` | Net position per instrument per client |
| `trades` | Ring buffer of last N trades (default 1000) |
| `price_history` | Ring buffer of last N mid prices per instrument (for PnL curve) |
| `pnl_history` | Timestamped total PnL snapshots |

### PnL Calculation
```
mark_to_market_pnl(instrument) = position(instrument) × (current_mid − avg_entry_price)
total_pnl = Σ mark_to_market_pnl(instrument)
```

### Metrics Computed
| Metric | Description |
|---|---|
| **Total PnL** | Sum of MTM PnL across all instruments |
| **PnL by instrument** | Per-instrument MTM contribution |
| **Net position** | Long/short per instrument in base currency units |
| **Client yield** | PnL attributed per client (spread captured: sell-to-client ask minus buy-from-client bid) |
| **Trade activity** | Trade count per client, per instrument, rolling window |
| **Spread captured** | Revenue from bid-ask spread per trade |

### API Endpoints

```
GET  /api/snapshot          → full current state (positions, PnL, prices)
GET  /api/pnl/history       → list of { ts, total_pnl } snapshots
GET  /api/positions         → { instrument: { net_qty, avg_entry, mtm_pnl } }
GET  /api/clients           → per-client stats
GET  /api/trades/recent     → last N trades
WS   /ws/live               → streams incremental updates (price ticks + trade events) to dashboard
```

### Throttling
- Backend rebroadcasts to the dashboard WebSocket at max **10 updates/second** (batching if streamer is faster).
- This prevents overwhelming Streamlit's rerun loop at scale.

---

## Service 3 — Dashboard (`src/dashboard/`)

**Purpose:** Streamlit app that subscribes to the backend and renders live metrics.

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  FINALTO — Risk Management Dashboard          [live dot] │
├────────────┬────────────┬────────────┬───────────────────┤
│ Total PnL  │ # Trades   │ Open Instr │  Largest Position │
│  (KPI)     │  (KPI)     │  (KPI)     │  (KPI)            │
├────────────┴────────────┴────────────┴───────────────────┤
│  PnL Curve (line chart, time-series, hover values)       │
├────────────────────────┬────────────────────────────────┤
│  Position by Instrument│  PnL Attribution (bar chart)   │
│  (horizontal bar chart)│  by instrument                 │
├────────────────────────┴────────────────────────────────┤
│  Client Yield Table (sortable, per-client PnL + trades)  │
├─────────────────────────────────────────────────────────┤
│  Recent Trades Feed (live scrolling table, last 50)      │
└─────────────────────────────────────────────────────────┘
```

### Chart Library
- **Apache ECharts** via `streamlit-echarts` — canvas-based, no remount flash, supports crosshair tooltips natively.

### Data Refresh Strategy
- Background thread subscribes to backend WebSocket and writes updates into module-level `_store` under `threading.Lock` (never `st.session_state` from a thread).
- Sidebar price ticker uses `@st.fragment(run_every="100ms")` (10 Hz, text only).
- Charts/tables use `@st.fragment(run_every="1s")` — ECharts canvas prevents remount flash at this rate.

```python
@st.fragment(run_every="1s")
def main_dashboard():
    with _lock:
        data = dict(_store)
    # render ECharts charts from data
```

- Backend throttle (`MAX_DASHBOARD_HZ=10`) caps rebroadcast regardless of streamer rate.
  At 60 ticks/sec from the streamer, internal state still updates at full rate but the
  dashboard WebSocket only receives up to 10 messages/sec.

---

## Docker Compose (`docker-compose.yml`)

```yaml
services:
  streamer:
    build: ./src/streamer
    ports: ["8001:8001"]
    environment:
      TICK_RATE_HZ: 1        # ticks per second per instrument
      NUM_CLIENTS: 5
      TRADE_PROBABILITY: 0.1

  backend:
    build: ./src/backend
    ports: ["8000:8000"]
    environment:
      STREAMER_WS_URL: ws://streamer:8001
      MAX_DASHBOARD_HZ: 10   # max rebroadcast rate to dashboard
    depends_on: [streamer]

  dashboard:
    build: ./src/dashboard
    ports: ["8501:8501"]
    environment:
      BACKEND_WS_URL: ws://backend:8000/ws/live
    depends_on: [backend]
```

Single command to run: `docker compose up --build`

---

## File / Directory Structure

```
/
├── plan.md
├── task.md
├── docker-compose.yml
├── AGENTS.md
├── REQUIREMENTS_CHECK.md
├── src/
│   ├── streamer/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py          # WebSocket server + GBM price/trade gen
│   │   └── listener.py      # Dev tool: CLI subscriber for debugging
│   ├── backend/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py          # FastAPI app, lifespan, broadcaster, WS endpoint
│   │   ├── state.py         # InstrumentPosition, ClientStats, AppState
│   │   ├── metrics.py       # apply_price_event, apply_trade_event, build_live_update
│   │   └── streamer_client.py  # Async WS consumer with auto-reconnect
│   └── dashboard/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── app.py           # Entry point: _store, _lock, WS thread, sidebar nav
│       ├── charts.py        # ECharts option builders, COLORS
│       └── views/
│           ├── overview.py      # KPIs, PnL curve, positions, sparklines
│           ├── instruments.py   # Per-instrument cards + price history chart
│           └── clients.py       # Client yield table + drill-down
└── README.md                # Setup and run instructions
```

---

## Key Dependencies

| Service | Package | Why |
|---|---|---|
| streamer | `websockets` | Async WebSocket server |
| backend | `fastapi`, `uvicorn[standard]` | Async HTTP + WebSocket |
| backend | `websockets` | Connect to streamer |
| dashboard | `streamlit` | UI framework |
| dashboard | `plotly` | Interactive charts with hover |
| dashboard | `websockets` | Connect to backend live feed |
| dashboard | `httpx` | Fetch initial snapshot from backend |

---

## Scalability Notes

- At **1 Hz × 3 instruments = 3 price ticks/sec** + ~1–2 trades/sec → easily handled by async Python.
- At **10× scale** (300 ticks/sec), the backend throttle (`MAX_DASHBOARD_HZ`) prevents the Streamlit loop from being overwhelmed — only the in-memory state is updated faster, and the dashboard always sees the latest state at its refresh rate.
- If the streamer volume grows further, the backend can switch from a WebSocket fan-out to a simple in-process queue without interface changes.

---

## Implementation Order

1. `services/streamer/main.py` — price + trade generator with WebSocket broadcast
2. `services/backend/` — state, metrics, FastAPI routes, streamer consumer
3. `services/dashboard/app.py` — Streamlit layout, charts, live WS subscription
4. `docker-compose.yml` + all `Dockerfile`s
5. `README.md` — one-command setup instructions

---

## What Will NOT Be Done (scope guard)

- No database / persistence (in-memory only, as required for MVP)
- No authentication
- No historical replay
- No frontend build pipeline (pure Python/Streamlit)
