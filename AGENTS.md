# AGENTS.md

Context for AI agents working on this repo.

---

## What It Is

Real-time risk dashboard — 3 services, Docker Compose, all Python.

| Service | Entry point | Port |
|---|---|---|
| Streamer | `src/streamer/main.py` | 8001 |
| Backend | `src/backend/main.py` | 8000 |
| Dashboard | `src/dashboard/app.py` | 8501 |

Services talk over WebSocket JSON only. No shared package, no database.

---

## Key Files

| File | Role |
|---|---|
| `src/streamer/main.py` | GBM price generator, client trade simulator, WS server |
| `src/backend/state.py` | All mutable state — `InstrumentPosition`, `ClientStats`, `AppState` |
| `src/backend/metrics.py` | Pure functions: `apply_price_event`, `apply_trade_event`, `build_live_update` |
| `src/backend/streamer_client.py` | Async WS consumer with auto-reconnect |
| `src/backend/main.py` | FastAPI app, lifespan, broadcaster, WS endpoint |
| `src/dashboard/app.py` | `_store`, `_lock`, `_ws_thread`, sidebar nav, `price_ticker()` |
| `src/dashboard/charts.py` | All ECharts option builders + `COLORS`, helpers |
| `src/dashboard/views/overview.py` | KPIs, PnL curve, position bars, sparklines |
| `src/dashboard/views/instruments.py` | Per-instrument detail cards + time-ranged price chart |
| `src/dashboard/views/clients.py` | Client yield table + per-client trade drill-down |

---

## Design Rules — Don't Break These

**Book convention:** client BUY → Finalto SHORT (net_qty decreases). Enforced in `state.py:apply_trade`. Flipping this breaks all PnL.

**Dashboard threading:** background `_ws_thread` writes only to module-level `_store` under `_lock`. Never write to `st.session_state` from a thread — silent failure in Streamlit.

**`asyncio.Event` lives in `lifespan()`** — not at module level. Must be created on the running event loop.

**Fragment rates:** `price_ticker` at `100ms` (text only, in sidebar), `main_dashboard` / page fragments at `1s` (ECharts + tables). Don't raise chart rate — it causes visible flicker.

**`_store` dict:** always mutate in place (`_store[key] = ...`). Never replace the dict object itself.

**ECharts keys:** charts inside `@st.fragment` need a stable `key=` to prevent remount flash. Use page-prefixed keys (`"ov_pnl_curve"`, `"inst_price_BTC/USD"`). Only omit `key` if you explicitly want a full remount on every tick.

**`pages/` folder:** Streamlit auto-discovers `.py` files in a folder named `pages/` and adds them as top-level nav. Our view modules live in `views/` to avoid this — do not rename back to `pages/`.

**`PYTHONPATH=/app`** is set in the dashboard Dockerfile so `from charts import ...` and `from views.x import ...` resolve correctly from both `app.py` and view modules.

---

## Wire Format

**Streamer → Backend** (`ws://streamer:8001`):
```json
{"type": "price", "instrument": "BTC/USD", "bid": 68100.5, "ask": 68110.5, "mid": 68105.0, "ts": 1712345678.1}
{"type": "trade", "client_id": "client_2", "instrument": "BTC/USD", "side": "BUY", "qty": 0.5, "price": 68110.5, "ts": 1712345678.4}
```

**Backend → Dashboard** (`ws://backend:8000/ws/live`):
```json
{"type": "snapshot", "total_pnl": 1234.5, "positions": {...}, "clients": {...}, "recent_trades": [...], "pnl_history": [...], "price_history": {...}}
{"type": "update",   "total_pnl": 1240.0, "positions": {...}, "clients": {...}, "latest_trade": {...}, "pnl_snapshot": {...}, "price_tick": {"BTC/USD": {"ts": ..., "mid": ...}, ...}}
```

Snapshot sent once on connect. Updates throttled at `MAX_DASHBOARD_HZ` (default 10). `price_tick` carries the latest price point per instrument so the dashboard can grow its local `price_history` deque without re-sending the full history on every tick.

---

## Extending

**Add a metric:** compute in `metrics.py` → include in `build_live_update()` + `snapshot()` → render in the relevant view.

**Add an instrument:** add to `INSTRUMENTS` in `src/streamer/main.py` and `COLORS` in `src/dashboard/charts.py`.

**Add a page:** create `src/dashboard/views/newpage.py` with a `render(store, lock)` function → add the nav option in `app.py` sidebar radio → add the import/route at the bottom of `app.py`.

**Stress test:** set `TICK_RATE_HZ=60` in `docker-compose.yml` — backend throttle keeps dashboard at ≤10 Hz.
