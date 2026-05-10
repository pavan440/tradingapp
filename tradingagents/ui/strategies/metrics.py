from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MomentumSummary:
    last_close: float
    ret_5d: float | None
    ret_21d: float | None
    ret_63d: float | None
    high_20d: float | None
    above_20d_high: bool | None


def _pct(a: float, b: float) -> float:
    return (a / b - 1.0) * 100.0 if b else 0.0


def compute_momentum_summary(hist: pd.DataFrame) -> MomentumSummary:
    hist = hist.dropna()
    if hist.empty or "Close" not in hist:
        return MomentumSummary(0.0, None, None, None, None, None)

    close = hist["Close"].astype(float)
    last_close = float(close.iloc[-1])

    def ret_n(n: int) -> float | None:
        if len(close) <= n:
            return None
        return round(_pct(last_close, float(close.iloc[-(n + 1)])), 2)

    high_20d = None
    above_20d_high = None
    if "High" in hist and len(hist) >= 22:
        high_20d = float(hist["High"].astype(float).rolling(20).max().iloc[-2])
        above_20d_high = last_close > high_20d

    return MomentumSummary(
        last_close=round(last_close, 2),
        ret_5d=ret_n(5),
        ret_21d=ret_n(21),
        ret_63d=ret_n(63),
        high_20d=round(high_20d, 2) if high_20d is not None else None,
        above_20d_high=above_20d_high,
    )


@dataclass(frozen=True)
class DayTradingSummary:
    atr14: float | None
    stop_1r: float | None
    stop_2r: float | None
    takeprofit_1r: float | None
    takeprofit_2r: float | None


def compute_atr14(hist: pd.DataFrame) -> float | None:
    hist = hist.dropna()
    if hist.empty or not {"High", "Low", "Close"}.issubset(hist.columns) or len(hist) < 20:
        return None
    high = hist["High"].astype(float)
    low = hist["Low"].astype(float)
    close = hist["Close"].astype(float)

    tr = pd.concat(
        [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr14 = tr.rolling(14).mean().iloc[-1]
    return float(atr14) if pd.notna(atr14) else None


def compute_day_trading_levels(last_price: float, atr14: float | None) -> DayTradingSummary:
    if atr14 is None or atr14 <= 0:
        return DayTradingSummary(None, None, None, None, None)
    # Simple risk ladder using ATR as 1R (intraday proxy).
    stop_1r = last_price - atr14
    stop_2r = last_price - 2 * atr14
    tp_1r = last_price + atr14
    tp_2r = last_price + 2 * atr14
    return DayTradingSummary(
        atr14=round(atr14, 2),
        stop_1r=round(stop_1r, 2),
        stop_2r=round(stop_2r, 2),
        takeprofit_1r=round(tp_1r, 2),
        takeprofit_2r=round(tp_2r, 2),
    )


@dataclass(frozen=True)
class BullBearSummary:
    bull_score: int
    bear_score: int
    notes: list[str]


def compute_bull_bear_scores(hist: pd.DataFrame) -> BullBearSummary:
    """
    Lightweight bull/bear calculator from daily data:
    - Trend: close vs 20/50 SMA
    - Momentum: 5d/21d returns
    - RSI-ish: overbought/oversold bands on 14D RSI
    """
    hist = hist.dropna()
    notes: list[str] = []
    bull = 0
    bear = 0

    if hist.empty or "Close" not in hist:
        return BullBearSummary(0, 0, ["No history"])

    close = hist["Close"].astype(float)
    last = float(close.iloc[-1])

    sma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
    sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    if sma20 is not None and pd.notna(sma20):
        if last > float(sma20):
            bull += 1
            notes.append("Close > 20SMA")
        else:
            bear += 1
            notes.append("Close < 20SMA")
    if sma50 is not None and pd.notna(sma50):
        if last > float(sma50):
            bull += 1
            notes.append("Close > 50SMA")
        else:
            bear += 1
            notes.append("Close < 50SMA")

    # Returns
    mom = compute_momentum_summary(hist)
    if mom.ret_5d is not None:
        if mom.ret_5d > 0:
            bull += 1
        else:
            bear += 1
        notes.append(f"5D return {mom.ret_5d:+.2f}%")
    if mom.ret_21d is not None:
        if mom.ret_21d > 0:
            bull += 1
        else:
            bear += 1
        notes.append(f"21D return {mom.ret_21d:+.2f}%")

    # RSI (14)
    if len(close) >= 30:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1])
        if rsi_val >= 70:
            bear += 1
            notes.append(f"RSI {rsi_val:.1f} (overbought)")
        elif rsi_val <= 30:
            bull += 1
            notes.append(f"RSI {rsi_val:.1f} (oversold)")
        else:
            notes.append(f"RSI {rsi_val:.1f} (neutral)")

    return BullBearSummary(bull_score=bull, bear_score=bear, notes=notes)
