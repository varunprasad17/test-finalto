"""
pages/clients.py — Client yield and trade history.

Top section: all clients ranked by spread captured.
Bottom section: selectbox to drill into one client's trade history.
"""

import threading
from typing import Any

import pandas as pd
import streamlit as st


def render(store: dict[str, Any], lock: threading.Lock) -> None:
    @st.fragment(run_every="1s")  # type: ignore[untyped-decorator]
    def _body() -> None:
        with lock:
            clients = dict(store["clients"])
            trades = list(store["recent_trades"])

        # --- Client yield table ------------------------------------------------
        st.markdown("#### Client Yield")
        if clients:
            df = pd.DataFrame(
                sorted(clients.values(), key=lambda c: c["spread_captured"], reverse=True)
            )[["client_id", "trade_count", "spread_captured"]]
            df.columns = ["Client", "Trades", "Spread Captured ($)"]
            st.dataframe(df, hide_index=True, use_container_width=True)
        else:
            st.info("Waiting for trade data…")

        st.divider()

        # --- Per-client trade history ------------------------------------------
        st.markdown("#### Trade History")
        if not trades:
            st.info("Waiting for trades…")
            return

        client_ids = sorted(clients.keys()) if clients else []
        if not client_ids:
            return

        selected = st.selectbox("Select client", client_ids, key="clients_select")

        client_trades = [t for t in trades if t.get("client_id") == selected]

        if client_trades:
            df_t = pd.DataFrame(client_trades)[["ts", "instrument", "side", "qty", "price"]]
            df_t.columns = ["Timestamp", "Instrument", "Side", "Qty", "Price ($)"]
            st.dataframe(df_t, hide_index=True, use_container_width=True)

            total_spread = clients.get(selected, {}).get("spread_captured", 0)
            trade_count = clients.get(selected, {}).get("trade_count", 0)
            m1, m2 = st.columns(2)
            m1.metric("Trades (all time)", trade_count)
            m2.metric("Total Spread Captured", f"${total_spread:,.2f}")
        else:
            st.info(f"No trades recorded for {selected} yet.")

    _body()
