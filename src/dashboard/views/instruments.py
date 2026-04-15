"""
views/instruments.py — Per-instrument live detail view.

One card per instrument: live bid/ask/mid, net position, avg entry prices,
MTM PnL, and a time-ranged price history chart.
"""

import threading
from typing import Any

from charts import COLORS, echarts_price_line
import streamlit as st
from streamlit_echarts import st_echarts

# Ticks are 1/sec per instrument.  Caps at however many are actually stored.
_RANGES = {"5 min": 300, "30 min": 1800, "1 hour": 3600}


def render(store: dict[str, Any], lock: threading.Lock) -> None:
    # Range selector lives outside the fragment so changing it re-renders immediately
    selected_range = st.radio(
        "Time range",
        list(_RANGES.keys()),
        horizontal=True,
        key="inst_range",
    )
    _RANGES[selected_range]

    @st.fragment(run_every="1s")  # type: ignore[untyped-decorator]
    def _body() -> None:
        with lock:
            positions = dict(store["positions"])
            price_history = {k: list(v) for k, v in store["price_history"].items()}

        if not positions:
            st.info("Waiting for instrument data…")
            return

        # Re-read the range selection each tick
        ticks = _RANGES.get(st.session_state.get("inst_range", "5 min"), 300)

        for inst, pos in positions.items():
            color = COLORS.get(inst, "#888")
            mid = pos.get("mid", 0)
            bid = pos.get("bid", 0)
            ask = pos.get("ask", 0)
            net = pos.get("net_qty", 0)
            mtm = pos.get("mtm_pnl", 0)
            avg_l = pos.get("avg_long_entry", 0)
            avg_s = pos.get("avg_short_entry", 0)
            hist = price_history.get(inst, [])[-ticks:]  # slice to selected range

            st.markdown(
                f"<span style='color:{color};font-size:20px;font-weight:bold'>{inst}</span>",
                unsafe_allow_html=True,
            )

            # Price strip
            p1, p2, p3 = st.columns(3)
            p1.metric("Mid", f"${mid:,.4f}")
            p2.metric("Bid", f"${bid:,.4f}")
            p3.metric("Ask", f"${ask:,.4f}")

            # Position stats
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Net Position", f"{net:,.4f}")
            s2.metric("MTM PnL", f"${mtm:,.2f}")
            s3.metric("Avg Long Entry", f"${avg_l:,.4f}" if avg_l else "—")
            s4.metric("Avg Short Entry", f"${avg_s:,.4f}" if avg_s else "—")

            if hist:
                st_echarts(
                    echarts_price_line(inst, hist), height="240px", key=f"inst_price_{inst}"
                )

            st.divider()

    _body()
