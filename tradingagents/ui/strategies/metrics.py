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


def compute_recent_returns(hist: pd.DataFrame, *, bars: int = 8) -> list[float]:
    hist = hist.dropna()
    if hist.empty or "Close" not in hist or len(hist) < 3:
        return []
    close = hist["Close"].astype(float)
    rets = close.pct_change().dropna().tail(bars) * 100.0
    return [round(float(x), 2) for x in rets.tolist()]


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


@dataclass(frozen=True)
class FakeMomentumSummary:
    bull_trap_score: int
    bear_trap_score: int
    bull_trap_reasons: list[str]
    bear_trap_reasons: list[str]


def compute_fake_momentum(hist: pd.DataFrame, *, lookback: int = 20) -> FakeMomentumSummary:
    """
    Detect likely "fake momentum" (bull/bear traps) using only OHLCV.

    Heuristics (each adds 1 point):
    - Breakout/breakdown vs lookback high/low without volume confirmation
    - Failed breakout/breakdown (close back inside range)
    - Wick rejection (upper wick for bull trap, lower wick for bear trap)
    - RSI divergence proxy (RSI extreme + turning)
    """
    hist = hist.dropna()
    if hist.empty or not {"Open", "High", "Low", "Close"}.issubset(hist.columns):
        return FakeMomentumSummary(0, 0, ["No history"], ["No history"])

    close = hist["Close"].astype(float)
    high = hist["High"].astype(float)
    low = hist["Low"].astype(float)
    open_ = hist["Open"].astype(float)
    volume = hist["Volume"].astype(float) if "Volume" in hist else None

    if len(hist) < lookback + 3:
        return FakeMomentumSummary(0, 0, ["Insufficient bars"], ["Insufficient bars"])

    last_close = float(close.iloc[-1])
    last_open = float(open_.iloc[-1])
    last_high = float(high.iloc[-1])
    last_low = float(low.iloc[-1])
    last_vol = float(volume.iloc[-1]) if volume is not None and pd.notna(volume.iloc[-1]) else None
    avg_vol = float(volume.rolling(lookback).mean().iloc[-2]) if volume is not None else None

    range_high = float(high.rolling(lookback).max().iloc[-2])
    range_low = float(low.rolling(lookback).min().iloc[-2])

    bull_score = 0
    bear_score = 0
    bull_reasons: list[str] = []
    bear_reasons: list[str] = []

    # Breakout / breakdown without volume
    if last_close > range_high:
        if avg_vol and last_vol is not None and last_vol < 1.2 * avg_vol:
            bull_score += 1
            bull_reasons.append("Breakout without volume confirmation")
    if last_close < range_low:
        if avg_vol and last_vol is not None and last_vol < 1.2 * avg_vol:
            bear_score += 1
            bear_reasons.append("Breakdown without volume confirmation")

    # Failed breakout/breakdown: intrabar excursion but close back inside
    if last_high > range_high and last_close <= range_high:
        bull_score += 1
        bull_reasons.append("Failed breakout (high > range, close back inside)")
    if last_low < range_low and last_close >= range_low:
        bear_score += 1
        bear_reasons.append("Failed breakdown (low < range, close back inside)")

    # Wick rejection
    candle_range = max(last_high - last_low, 1e-9)
    upper_wick = last_high - max(last_open, last_close)
    lower_wick = min(last_open, last_close) - last_low
    if upper_wick / candle_range >= 0.45 and last_close < last_open:
        bull_score += 1
        bull_reasons.append("Upper-wick rejection (bull trap risk)")
    if lower_wick / candle_range >= 0.45 and last_close > last_open:
        bear_score += 1
        bear_reasons.append("Lower-wick rejection (bear trap risk)")

    # RSI extreme + turning (very lightweight divergence proxy)
    if len(close) >= 30:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        rsi_last = float(rsi.iloc[-1])
        rsi_prev = float(rsi.iloc[-2])
        if rsi_last >= 70 and rsi_last < rsi_prev:
            bull_score += 1
            bull_reasons.append("RSI rolling over from overbought")
        if rsi_last <= 30 and rsi_last > rsi_prev:
            bear_score += 1
            bear_reasons.append("RSI bouncing from oversold")

    return FakeMomentumSummary(
        bull_trap_score=bull_score,
        bear_trap_score=bear_score,
        bull_trap_reasons=bull_reasons,
        bear_trap_reasons=bear_reasons,
    )


@dataclass(frozen=True)
class CryptoSummary:
    ret_1d: float | None
    ret_7d: float | None
    ret_30d: float | None
    vol_7d_annualized: float | None
    volume_spike: float | None


def compute_crypto_summary(hist: pd.DataFrame) -> CryptoSummary:
    """
    Crypto-oriented summary from OHLCV bars:
    - 1D/7D/30D returns (where possible)
    - 7D realized vol (annualized) from bar-to-bar returns
    - volume spike = last volume / 20-bar avg volume
    """
    hist = hist.dropna()
    if hist.empty or "Close" not in hist:
        return CryptoSummary(None, None, None, None, None)

    close = hist["Close"].astype(float)
    last = float(close.iloc[-1])

    def ret_n(n: int) -> float | None:
        if len(close) <= n:
            return None
        prev = float(close.iloc[-(n + 1)])
        return round(_pct(last, prev), 2)

    # Realized vol: use last ~7 "days" worth of bars; for intraday this is approximate.
    returns = close.pct_change().dropna()
    vol_7d = None
    if len(returns) >= 30:
        window = returns.tail(7 * 24 if len(returns) > 7 * 24 else 50)
        sigma = float(window.std())
        # Annualize assuming 365 days and 24h sessions: a rough but stable heuristic.
        vol_7d = round(sigma * (365**0.5) * 100.0, 2)

    vol_spike = None
    if "Volume" in hist and len(hist) >= 25:
        vol = hist["Volume"].astype(float)
        avg = float(vol.rolling(20).mean().iloc[-2])
        lastv = float(vol.iloc[-1])
        if avg > 0:
            vol_spike = round(lastv / avg, 2)

    return CryptoSummary(
        ret_1d=ret_n(1),
        ret_7d=ret_n(7),
        ret_30d=ret_n(30),
        vol_7d_annualized=vol_7d,
        volume_spike=vol_spike,
    )
