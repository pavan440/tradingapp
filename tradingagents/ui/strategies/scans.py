from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finvizfinance.screener.overview import Overview


@dataclass(frozen=True)
class ScanStrategy:
    label: str
    signal: str | None = None
    filters_dict: dict[str, Any] | None = None
    limit: int = 50


SCAN_STRATEGIES: list[ScanStrategy] = [
    ScanStrategy(
        label="Penny Stock Catalyst Runners (Under $10, High Vol)",
        signal="Top Gainers",
        filters_dict={"Price": "Under $10", "Relative Volume": "Over 2"},
    ),
    ScanStrategy(
        label="Large/Mid Cap Momentum (Unusual Volume)",
        signal="Unusual Volume",
        filters_dict={"Market Cap.": "+Mid (over $2bln)", "Relative Volume": "Over 2"},
    ),
    ScanStrategy(
        label="Optionable Top Losers (High Volatility)",
        signal="Top Losers",
        filters_dict={"Option/Short": "Optionable", "Relative Volume": "Over 2"},
    ),
    ScanStrategy(
        label="📅 Earnings This Week (Penny/Micro Cap)",
        filters_dict={"Earnings Date": "This Week", "Market Cap.": "Micro (under $300mln)"},
        limit=1000
    ),
    ScanStrategy(
        label="📅 Earnings This Week (Small Cap)",
        filters_dict={"Earnings Date": "This Week", "Market Cap.": "Small ($300mln to $2bln)"},
        limit=1000
    ),
    ScanStrategy(
        label="📅 Earnings This Week (Mid Cap)",
        filters_dict={"Earnings Date": "This Week", "Market Cap.": "Mid ($2bln to $10bln)"},
        limit=1000
    ),
    ScanStrategy(
        label="📅 Earnings This Week (Large/Mega Cap)",
        filters_dict={"Earnings Date": "This Week", "Market Cap.": "+Large (over $10bln)"},
        limit=1000
    ),
    ScanStrategy(
        label="Relative Strength Leaders (S&P 500, Unusual Volume)",
        signal="Unusual Volume",
        filters_dict={"Index": "S&P 500", "Relative Volume": "Over 2"},
    ),
    ScanStrategy(
        label="High Short Interest (Optionable, Small/Mid)",
        signal="Most Shorted",
        filters_dict={"Option/Short": "Optionable", "Market Cap.": "+Small (over $300mln)"},
    ),
    ScanStrategy(
        label="📉 Significant Drop Today (> 5%)",
        filters_dict={"Change": "Down 5%"},
    ),
    ScanStrategy(
        label="📉 Significant Drop Today (> 10%)",
        filters_dict={"Change": "Down 10%"},
    ),
    ScanStrategy(
        label="📉 Massive Drop Today (> 20%)",
        filters_dict={"Change": "Down 20%"},
    ),
]


def run_scan(strategy: ScanStrategy):
    foverview = Overview()
    if strategy.signal:
        foverview.set_filter(signal=strategy.signal, filters_dict=strategy.filters_dict or {})
    else:
        foverview.set_filter(filters_dict=strategy.filters_dict or {})
    return foverview.screener_view(limit=strategy.limit, sleep_sec=0)

