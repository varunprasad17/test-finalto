"""
views/overview.py — Finalto PnL dashboard.

KPIs, PnL curve, net position bar, PnL attribution, price sparklines.
"""

import threading
from typing import Any

from charts import (
    echarts_pnl_attribution,
    echarts_pnl_curve,
    echarts_position_bar,
    echarts_sparkline,
)
import streamlit as st
from streamlit_echarts import st_echarts


def render(store: dict[str, Any], lock: threading.Lock) -> None:
    @st.fragment(run_every="1s")  # type: ignore[untyped-decorator]
    def _body() -> None:
        with lock:
            total_pnl = store["total_pnl"]
            positions = dict(store["positions"])
            clients = dict(store["clients"])
            pnl_history = list(store["pnl_history"])
            price_history = {k: list(v) for k, v in store["price_history"].items()}

        total_trades = sum(c["trade_count"] for c in clients.values())
        top_client = max(clients.values(), key=lambda c: c["spread_captured"], default=None)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total PnL", f"${total_pnl:,.2f}")
        k2.metric("Instruments", len(positions))
        k3.metric("Total Trades", total_trades)
        k4.metric(
            "Top Client (spread)",
            top_client["client_id"] if top_client else "—",
            f"${top_client['spread_captured']:,.2f}" if top_client else "",
        )

        st.divider()

        # PnL curve
        if pnl_history:
            st_echarts(echarts_pnl_curve(pnl_history), height="280px", key="ov_pnl_curve")
        else:
            st.info("Waiting for PnL data…")

        # Position bar + PnL attribution
        if positions:
            c_left, c_right = st.columns(2)
            with c_left:
                st_echarts(echarts_position_bar(positions), height="260px", key="ov_pos_bar")
            with c_right:
                st_echarts(echarts_pnl_attribution(positions), height="260px", key="ov_pnl_attr")

        # Sparklines
        if positions and price_history:
            st.markdown("#### Price History")
            cols = st.columns(len(positions))
            for col, inst in zip(cols, positions.keys(), strict=False):
                hist = price_history.get(inst, [])
                with col:
                    st.markdown(f"**{inst}**")
                    if hist:
                        st_echarts(
                            echarts_sparkline(inst, hist), height="80px", key=f"ov_spark_{inst}"
                        )

    _body()
