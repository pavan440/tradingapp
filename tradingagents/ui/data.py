from __future__ import annotations

import pandas as pd
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=3600)
def get_sector_performance():
    from finvizfinance.group.performance import Performance

    return Performance().screener_view(group="Sector")


@st.cache_data(ttl=3600)
def get_stock_info(ticker: str):
    return yf.Ticker(ticker).info


@st.cache_data(ttl=300)
def get_crypto_performance():
    try:
        from finvizfinance.crypto import Crypto

        return Crypto().performance()
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_market_indices():
    tickers = yf.Tickers("SPY QQQ DIA")
    data: list[dict] = []
    for t in ["SPY", "QQQ", "DIA"]:
        try:
            hist = tickers.tickers[t].history(period="2d")
            if len(hist) >= 2:
                prev_close = hist["Close"].iloc[-2]
                current = hist["Close"].iloc[-1]
                pct_change = ((current - prev_close) / prev_close) * 100
                data.append({"Ticker": t, "Price": current, "Change": pct_change})
        except Exception:
            continue
    return data


@st.cache_data(ttl=300)
def get_sp500_top_gainers():
    from finvizfinance.screener.overview import Overview

    try:
        foverview = Overview()
        foverview.set_filter(signal="Top Gainers", filters_dict={"Index": "S&P 500"})
        df = foverview.screener_view(limit=10, sleep_sec=0)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_options_flow():
    from finvizfinance.screener.overview import Overview

    foverview = Overview()
    foverview.set_filter(signal="Most Active", filters_dict={"Option/Short": "Optionable"})
    try:
        df = foverview.screener_view(limit=25, sleep_sec=0)
    except Exception:
        return pd.DataFrame()

    results: list[dict] = []
    if df is not None and not df.empty:
        tickers = df["Ticker"].tolist()
        for t in tickers:
            try:
                stock = yf.Ticker(t)
                expirations = stock.options
                if expirations:
                    chain = stock.option_chain(expirations[0])
                    call_oi = chain.calls["openInterest"].sum()
                    put_oi = chain.puts["openInterest"].sum()

                    results.append(
                        {
                            "Ticker": t,
                            "Call OI": int(call_oi),
                            "Put OI": int(put_oi),
                            "P/C Ratio": round(put_oi / call_oi, 2) if call_oi > 0 else 0,
                        }
                    )
            except Exception:
                continue
    return pd.DataFrame(results)

