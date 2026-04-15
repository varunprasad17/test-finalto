# Finalto — Risk Management Dashboard

Real-time risk dashboard for a market-making desk. Three Python services stream live prices, simulate client trades, and display book metrics in a browser.

## Quick Start

```bash
docker compose up --build
```

Open **http://localhost:8501**.

Force full rebuild: `docker compose build --no-cache && docker compose up`

**Local (no Docker):**
```bash
pip install -r requirements.txt
cd src/streamer  && python3 main.py
cd src/backend   && python3 main.py
cd src/dashboard && streamlit run app.py
```

---

## Architecture

```
Streamer :8001  ──WS──►  Backend :8000  ──WS──►  Dashboard :8501
```

| Service | Stack | Role |
|---|---|---|
| `src/streamer` | Python + websockets | Generates mock prices & trades |
| `src/backend` | FastAPI + uvicorn | Aggregates state, serves REST + WS API |
| `src/dashboard` | Streamlit + ECharts | Live charts and tables |

**Book convention:** client BUY → Finalto SHORT · client SELL → Finalto LONG

---

## Dashboard Pages

Sidebar navigation with live price ticker (updates at 100ms).

### Overview
- KPIs — Total PnL, instrument count, trade count, top client
- PnL curve — time-series with crosshair tooltip
- Net position — long/short bar per instrument
- PnL attribution — MTM contribution per instrument
- Price sparklines — rolling mid-price per instrument

### Instruments
- Per-instrument cards: live bid/ask/mid, net position, avg entry prices, MTM PnL
- Full price history chart with **1 min / 15 min / 1 hour** time-range selector

### Clients
- Client yield table ranked by spread captured
- Per-client drill-down: filtered trade history + lifetime metrics

Charts update at 1s via `@st.fragment(run_every="1s")`. Canvas rendering (ECharts) means no remount flash.

---

## Configuration

| Variable | Service | Default | Description |
|---|---|---|---|
| `TICK_RATE_HZ` | streamer | `1` | Price ticks/sec per instrument |
| `NUM_CLIENTS` | streamer | `5` | Number of simulated clients |
| `TRADE_PROBABILITY` | streamer | `0.15` | Chance a client trades per tick |
| `MAX_DASHBOARD_HZ` | backend | `10` | Max update rate to dashboard |
| `STREAMER_WS_URL` | backend | `ws://localhost:8001` | Streamer address |
| `BACKEND_WS_URL` | dashboard | `ws://localhost:8000/ws/live` | Backend live feed |

Stress test: set `TICK_RATE_HZ=60` — internal state updates at full rate, dashboard stays capped at 10 Hz.

---

## Backend REST API

```
GET  /health               → {"status": "ok"}
GET  /api/snapshot         → full current state
GET  /api/positions        → net qty, avg entry, MTM PnL per instrument
GET  /api/clients          → trade count, spread captured per client
GET  /api/trades/recent    → last 50 trades
GET  /api/pnl/history      → timestamped PnL series
WS   /ws/live              → throttled live update stream
```

---

## Instruments

| Symbol | Mid | Half-spread | Volatility/tick |
|---|---|---|---|
| BTC/USD | $68,000 | $5.00 | $150 |
| GOLD/USD | $2,300 | $0.50 | $5 |
| MSFT/USD | $420 | $0.05 | $1.50 |

To add an instrument: add to `INSTRUMENTS` in `src/streamer/main.py` and `COLORS` in `src/dashboard/charts.py`.

---

## Debug Streamer

```bash
python3 src/streamer/listener.py          # connect to localhost:8001
python3 src/streamer/listener.py ws://host:8001  # custom host
```
