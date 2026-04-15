"""
charts.py — ECharts option builders for the Finalto dashboard.
All functions are pure: take data, return an Apache ECharts option dict.
"""

import datetime
from typing import Any


def _fmt_ts(ts: float) -> str:
    """Unix timestamp → 'HH:MM:SS' local time string."""
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


COLORS = {
    "BTC/USD": "#F7931A",
    "GOLD/USD": "#FFD700",
    "MSFT/USD": "#00A4EF",
}

_BG = "#0e1117"


def pnl_color(val: float) -> str:
    return "#26a69a" if val >= 0 else "#ef5350"


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def echarts_pnl_curve(pnl_history: list[dict[str, Any]]) -> dict[str, Any]:
    xs = [_fmt_ts(h["ts"]) for h in pnl_history]
    ys = [round(h["total_pnl"], 2) for h in pnl_history]
    color = pnl_color(ys[-1] if ys else 0)
    return {
        "backgroundColor": _BG,
        "title": {"text": "Total PnL Over Time", "textStyle": {"color": "#ccc", "fontSize": 13}},
        "tooltip": {
            "trigger": "axis",
            "formatter": "PnL: <b>${c}</b>",
            "axisPointer": {"type": "cross", "lineStyle": {"color": "#555"}},
        },
        "grid": {"left": 75, "right": 20, "top": 45, "bottom": 35},
        "xAxis": {
            "type": "category",
            "data": xs,
            "axisLabel": {
                "color": "#555",
                "fontSize": 10,
                "showMaxLabel": True,
                "showMinLabel": True,
                "interval": "auto",
            },
            "axisLine": {"lineStyle": {"color": "#222"}},
            "boundaryGap": False,
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": "#888", "formatter": "${value}"},
            "splitLine": {"lineStyle": {"color": "#1a1a1a"}},
        },
        "series": [
            {
                "type": "line",
                "data": ys,
                "smooth": True,
                "symbol": "none",
                "lineStyle": {"color": color, "width": 2},
                "areaStyle": {
                    "color": {
                        "type": "linear",
                        "x": 0,
                        "y": 0,
                        "x2": 0,
                        "y2": 1,
                        "colorStops": [
                            {"offset": 0, "color": rgba(color, 0.35)},
                            {"offset": 1, "color": rgba(color, 0.02)},
                        ],
                    }
                },
            }
        ],
    }


def echarts_position_bar(positions: dict[str, Any]) -> dict[str, Any]:
    instruments = list(positions.keys())
    net_qtys = [round(positions[i]["net_qty"], 4) for i in instruments]
    return {
        "backgroundColor": _BG,
        "title": {
            "text": "Net Position by Instrument",
            "textStyle": {"color": "#ccc", "fontSize": 13},
        },
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>Net qty: <b>{c}</b>"},
        "grid": {"left": 75, "right": 20, "top": 45, "bottom": 35},
        "xAxis": {
            "type": "category",
            "data": instruments,
            "axisLabel": {"color": "#ccc"},
            "axisLine": {"lineStyle": {"color": "#222"}},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": "#888"},
            "splitLine": {"lineStyle": {"color": "#1a1a1a"}},
        },
        "series": [
            {
                "type": "bar",
                "data": [{"value": v, "itemStyle": {"color": pnl_color(v)}} for v in net_qtys],
                "barMaxWidth": 60,
            }
        ],
    }


def echarts_pnl_attribution(positions: dict[str, Any]) -> dict[str, Any]:
    instruments = list(positions.keys())
    pnls = [round(positions[i]["mtm_pnl"], 2) for i in instruments]
    return {
        "backgroundColor": _BG,
        "title": {
            "text": "PnL Attribution by Instrument",
            "textStyle": {"color": "#ccc", "fontSize": 13},
        },
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>MTM PnL: <b>${c}</b>"},
        "grid": {"left": 85, "right": 20, "top": 45, "bottom": 35},
        "xAxis": {
            "type": "category",
            "data": instruments,
            "axisLabel": {"color": "#ccc"},
            "axisLine": {"lineStyle": {"color": "#222"}},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": "#888", "formatter": "${value}"},
            "splitLine": {"lineStyle": {"color": "#1a1a1a"}},
        },
        "series": [
            {
                "type": "bar",
                "data": [
                    {"value": v, "itemStyle": {"color": COLORS.get(i, "#888")}}
                    for i, v in zip(instruments, pnls, strict=False)
                ],
                "barMaxWidth": 60,
            }
        ],
    }


def echarts_sparkline(instrument: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    ys = [round(h["mid"], 4) for h in history]
    color = COLORS.get(instrument, "#888")
    return {
        "backgroundColor": _BG,
        "grid": {"left": 0, "right": 0, "top": 2, "bottom": 2},
        "xAxis": {
            "type": "category",
            "show": False,
            "data": list(range(len(ys))),
            "boundaryGap": False,
        },
        "yAxis": {"type": "value", "show": False, "scale": True},
        "tooltip": {"trigger": "axis", "formatter": "${c}"},
        "series": [
            {
                "type": "line",
                "data": ys,
                "smooth": True,
                "symbol": "none",
                "lineStyle": {"color": color, "width": 1.5},
                "areaStyle": {"color": rgba(color, 0.12)},
            }
        ],
    }


def echarts_price_line(instrument: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    """Larger price history chart for the Instruments page."""
    xs = [_fmt_ts(h["ts"]) for h in history]
    ys = [round(h["mid"], 4) for h in history]
    color = COLORS.get(instrument, "#888")
    return {
        "backgroundColor": _BG,
        "title": {
            "text": f"{instrument} — Mid Price",
            "textStyle": {"color": "#ccc", "fontSize": 13},
        },
        "tooltip": {
            "trigger": "axis",
            "formatter": "{b}<br/>$ {c}",
            "axisPointer": {"type": "cross", "lineStyle": {"color": "#555"}},
        },
        "grid": {"left": 75, "right": 20, "top": 45, "bottom": 35},
        "xAxis": {
            "type": "category",
            "data": xs,
            "axisLabel": {
                "color": "#555",
                "fontSize": 10,
                "showMaxLabel": True,
                "showMinLabel": True,
                "interval": "auto",
            },
            "axisLine": {"lineStyle": {"color": "#222"}},
            "boundaryGap": False,
        },
        "yAxis": {
            "type": "value",
            "scale": True,
            "axisLabel": {"color": "#888", "formatter": "${value}"},
            "splitLine": {"lineStyle": {"color": "#1a1a1a"}},
        },
        "series": [
            {
                "type": "line",
                "data": ys,
                "smooth": True,
                "symbol": "none",
                "lineStyle": {"color": color, "width": 2},
                "areaStyle": {"color": rgba(color, 0.12)},
            }
        ],
    }
