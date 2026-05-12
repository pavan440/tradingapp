from __future__ import annotations

import datetime
import sys

import streamlit as st
from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients.factory import create_llm_client

from tradingagents.ui.data import (
    get_crypto_performance,
    get_market_indices,
    get_options_flow,
    get_sector_performance,
    get_sp500_top_gainers,
    get_stock_info,
)
from tradingagents.ui.streamlit_utils import StreamlitRedirect, check_dataframe_click
from tradingagents.ui.strategies.scans import SCAN_STRATEGIES, run_scan
from tradingagents.ui.strategies.metrics import (
    compute_atr14,
    compute_bull_bear_scores,
    compute_crypto_summary,
    compute_day_trading_levels,
    compute_fake_momentum,
    compute_momentum_summary,
    compute_recent_returns,
)


def main() -> None:
    load_dotenv(override=True)

    page = st.sidebar.radio("Navigation", ["🔍 Market Scanner", "🤖 Agent Execution"])

    if page == "🔍 Market Scanner":
        _render_market_scanner()
    else:
        _render_agent_execution()


def _render_market_scanner() -> None:
    try:
        import finvizfinance  # noqa: F401
    except Exception:
        st.error("Please install finvizfinance using: pip install finvizfinance")
        return

    if "all_tickers" not in st.session_state:
        st.session_state["all_tickers"] = set(["NVDA", "AAPL", "MSFT", "TSLA", "AMD", "SPY", "QQQ"])

    st.title("🔍 Global Market Scanner")
    st.markdown("Filter the market for trending plays, penny stocks, and earnings momentum.")

    st.subheader("📈 Major Indices")
    indices = get_market_indices()
    if indices:
        for idx in indices:
            st.session_state["all_tickers"].add(idx["Ticker"])
        cols = st.columns(len(indices))
        for i, col in enumerate(cols):
            col.metric(indices[i]["Ticker"], f"${indices[i]['Price']:.2f}", f"{indices[i]['Change']:.2f}%")
    st.markdown("---")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📊 Sector Performance Graph")
        try:
            perf_df = get_sector_performance()
            st.bar_chart(perf_df.set_index("Name")["Change"])
        except Exception as e:
            st.warning(f"Could not load sector performance: {e}")

    with c2:
        st.subheader("🚀 Top S&P 500 Movers (Price Change)")
        try:
            sp500_df = get_sp500_top_gainers()
            if not sp500_df.empty:
                st.session_state["all_tickers"].update(sp500_df["Ticker"].tolist())
                sp500_df = sp500_df.sort_values("Change", ascending=False)
                st.bar_chart(sp500_df.set_index("Ticker")["Change"])
        except Exception as e:
            st.warning(f"Could not load S&P 500 movers: {e}")

    st.markdown("---")
    st.subheader("🪙 Crypto Overview")
    try:
        crypto_df = get_crypto_performance()
        if crypto_df is not None and not crypto_df.empty:
            top_gainers = crypto_df.nlargest(15, "Perf Day")
            top_losers = crypto_df.nsmallest(15, "Perf Day")

            top_gainers["Perf Day"] = (top_gainers["Perf Day"] * 100).round(2).astype(str) + "%"
            top_losers["Perf Day"] = (top_losers["Perf Day"] * 100).round(2).astype(str) + "%"

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Top Gainers (24H)**")
                evt1 = st.dataframe(
                    top_gainers[["Ticker", "Price", "Perf Day"]],
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                )
                check_dataframe_click(evt1, top_gainers)
                st.session_state["all_tickers"].update(top_gainers["Ticker"].tolist())
            with c2:
                st.markdown("**Top Losers (24H)**")
                evt2 = st.dataframe(
                    top_losers[["Ticker", "Price", "Perf Day"]],
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                )
                check_dataframe_click(evt2, top_losers)
                st.session_state["all_tickers"].update(top_losers["Ticker"].tolist())
    except Exception as e:
        st.warning(f"Could not load crypto overview: {e}")

    st.markdown("---")
    st.subheader("📊 Options Flow Scanner")
    st.markdown("Scanning the most active optionable stocks to track Open Interest on Calls and Puts.")

    if st.button("🚀 Scan Call/Put Open Interest", type="primary"):
        with st.spinner("Analyzing options chains for the most active stocks... (This takes 10-15 seconds)"):
            flow_df = get_options_flow()
            if not flow_df.empty:
                st.session_state["options_flow_df"] = flow_df
                st.session_state["all_tickers"].update(flow_df["Ticker"].tolist())
            else:
                st.warning(
                    "Could not retrieve options data. The market may be closed or Yahoo Finance is rate-limiting."
                )

    if "options_flow_df" in st.session_state and not st.session_state["options_flow_df"].empty:
        flow_df = st.session_state["options_flow_df"]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🔥 Highest Call Interest**")
            call_heavy = flow_df.nlargest(10, "Call OI")
            evt3 = st.dataframe(
                call_heavy[["Ticker", "Call OI", "P/C Ratio"]],
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )
            check_dataframe_click(evt3, call_heavy)

        with col2:
            st.markdown("**🩸 Highest Put Interest**")
            put_heavy = flow_df.nlargest(10, "Put OI")
            evt4 = st.dataframe(
                put_heavy[["Ticker", "Put OI", "P/C Ratio"]],
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )
            check_dataframe_click(evt4, put_heavy)

    st.markdown("---")
    st.subheader("🎯 Stock Screener")

    labels = [s.label for s in SCAN_STRATEGIES]
    scan_label = st.selectbox("Select Scan Strategy", labels)
    scan_strategy = next(s for s in SCAN_STRATEGIES if s.label == scan_label)

    if st.button("🚀 Run Scanner", type="primary"):
        with st.spinner("Scanning market data..."):
            try:
                df = run_scan(scan_strategy)
                if df is not None and not df.empty:
                    st.success(f"Found {len(df)} stocks matching your criteria!")
                    evt5 = st.dataframe(df, on_select="rerun", selection_mode="single-row")
                    check_dataframe_click(evt5, df)
                    st.session_state["scanned_df"] = df
                    st.session_state["last_scan_label"] = scan_label
                    st.session_state["all_tickers"].update(df["Ticker"].tolist())
                else:
                    st.warning("No stocks found matching these criteria at the moment.")
                    st.session_state["scanned_df"] = None
            except Exception as e:
                st.error(f"Scanner Error: {str(e)}")

    elif "scanned_df" in st.session_state and st.session_state["scanned_df"] is not None:
        st.success(f"Found {len(st.session_state['scanned_df'])} stocks matching your criteria!")
        evt6 = st.dataframe(st.session_state["scanned_df"], on_select="rerun", selection_mode="single-row")
        check_dataframe_click(evt6, st.session_state["scanned_df"])
        
        if "Earnings" in st.session_state.get("last_scan_label", ""):
            st.markdown("### 🤖 Agentic Earnings Analyzer")
            st.write("Automatically analyze the top 5 stocks from this earnings list and categorize them into Bullish or Bearish based on fundamentals and news.")
            llm_provider_earn = st.selectbox("LLM Provider for Analysis", ["openrouter", "nebius", "openai", "anthropic", "google"], index=0, key="llm_earn")
            if st.button("🧠 Segregate Earnings (Bullish vs Bearish)", type="primary"):
                _run_agentic_earnings_analysis(st.session_state["scanned_df"], llm_provider_earn)

    st.markdown("---")
    st.subheader("🛠️ Custom Screener Builder & Profile")
    st.markdown("Combine multiple filters dynamically, run them, and save them to your database profile!")
    
    tab_build, tab_saved = st.tabs(["⚙️ Build Screener", "📁 My Saved Screeners"])
    
    with tab_build:
        c1, c2, c3 = st.columns(3)
        mc = c1.selectbox("Market Cap", ["Any", "Mega (over $200bln)", "Large ($10bln to $200bln)", "Mid ($2bln to $10bln)", "Small ($300mln to $2bln)", "Micro (under $300mln)", "Nano (under $50mln)"])
        price = c2.selectbox("Price", ["Any", "Under $5", "Under $10", "Under $20", "Over $20", "Over $50"])
        avg_vol = c3.selectbox("Average Volume", ["Any", "Over 100K", "Over 500K", "Over 1M", "Over 2M", "Over 5M", "Over 10M"])
        
        c4, c5, c6 = st.columns(3)
        exch = c4.selectbox("Exchange", ["Any", "AMEX", "NASDAQ", "NYSE"])
        sec = c5.selectbox("Sector", ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"])
        change = c6.selectbox("Performance (Change)", ["Any", "Down 5%", "Down 10%", "Down 15%", "Down >20%", "Up 5%", "Up 10%", "Up 15%", "Up >20%"])
        
        custom_filters = {}
        if mc != "Any": custom_filters["Market Cap."] = mc
        if price != "Any": custom_filters["Price"] = price
        if avg_vol != "Any": custom_filters["Average Volume"] = avg_vol
        if exch != "Any": custom_filters["Exchange"] = exch
        if sec != "Any": custom_filters["Sector"] = sec
        if change != "Any": custom_filters["Change"] = change.replace(">", "")
        
        col_run, col_save, _ = st.columns([2, 3, 5])
        if col_run.button("🔍 Run Custom Screener", type="primary"):
            with st.spinner("Running custom screener..."):
                try:
                    from finvizfinance.screener.overview import Overview
                    foverview = Overview()
                    if custom_filters:
                        foverview.set_filter(filters_dict=custom_filters)
                    df = foverview.screener_view(limit=200)
                    st.session_state["custom_builder_df"] = df
                except Exception as e:
                    st.error(f"Error running screener: {e}")
                    
        if "custom_builder_df" in st.session_state and st.session_state["custom_builder_df"] is not None:
            df = st.session_state["custom_builder_df"]
            if not df.empty:
                st.success(f"Found {len(df)} stocks!")
                evt_c = st.dataframe(df, on_select="rerun", selection_mode="single-row")
                check_dataframe_click(evt_c, df)
                st.session_state["all_tickers"].update(df["Ticker"].tolist())
            else:
                st.warning("No stocks found matching these exact criteria.")
                    
        with col_save.popover("💾 Save to Profile"):
            s_name = st.text_input("Name your screener")
            if st.button("Save Now"):
                from tradingagents.ui.auth import save_custom_scanner
                save_custom_scanner(st.session_state.username, s_name, custom_filters)
                st.success("Saved successfully!")
                st.rerun()

    with tab_saved:
        from tradingagents.ui.auth import get_custom_scanners
        saved_scanners = get_custom_scanners(st.session_state.username)
        if not saved_scanners:
            st.info("You don't have any saved screeners yet. Build one in the other tab!")
        else:
            for s in saved_scanners:
                with st.expander(f"📁 {s['name']} (Created: {s['created_at'][:10]})"):
                    st.write("**Filters applied:**", s['filters'])
                    if st.button(f"🚀 Run '{s['name']}'", key=f"run_s_{s['id']}"):
                        with st.spinner("Running saved screener..."):
                            try:
                                from finvizfinance.screener.overview import Overview
                                foverview = Overview()
                                if s['filters']:
                                    foverview.set_filter(filters_dict=s['filters'])
                                df = foverview.screener_view(limit=200)
                                st.session_state[f"saved_screener_df_{s['id']}"] = df
                            except Exception as e:
                                st.error(f"Error running screener: {e}")
                                
                    if f"saved_screener_df_{s['id']}" in st.session_state and st.session_state[f"saved_screener_df_{s['id']}"] is not None:
                        df = st.session_state[f"saved_screener_df_{s['id']}"]
                        if not df.empty:
                            st.success(f"Found {len(df)} stocks!")
                            evt_s = st.dataframe(df, on_select="rerun", selection_mode="single-row")
                            check_dataframe_click(evt_s, df)
                            st.session_state["all_tickers"].update(df["Ticker"].tolist())
                        else:
                            st.warning("No stocks found matching these criteria today.")

    st.markdown("---")
    
    if st.session_state.get("scroll_to_deep_dive"):
        import streamlit.components.v1 as components
        components.html(
            """
            <script>
                const elements = window.parent.document.querySelectorAll('h3');
                for (let el of elements) {
                    if (el.innerText.includes('Deep Dive & Strategy Setup')) {
                        el.scrollIntoView({behavior: 'smooth', block: 'start'});
                        break;
                    }
                }
            </script>
            """,
            height=0
        )
        st.session_state["scroll_to_deep_dive"] = False
        
    st.subheader("🕵️ Deep Dive & Strategy Setup")

    ticker_list = sorted(list(st.session_state.get("all_tickers", ["NVDA"])))
    default_tick = st.session_state.get("target_ticker", ticker_list[0] if ticker_list else "NVDA")
    if default_tick not in ticker_list:
        ticker_list.append(default_tick)
        ticker_list = sorted(ticker_list)

    default_index = ticker_list.index(default_tick) if default_tick in ticker_list else 0
    selected_ticker = st.selectbox(
        "Select ANY stock you see above (or click a table row above) to analyze:",
        ticker_list,
        index=default_index,
    )

    if not selected_ticker:
        return

    st.session_state["target_ticker"] = selected_ticker
    with st.spinner(f"Fetching quick snapshot for {selected_ticker}..."):
        try:
            info = get_stock_info(selected_ticker)
            st.markdown(f"**Quick Fundamental & Technical Snapshot for {selected_ticker}**")
            
            # Sector and Industry
            sector = info.get('sector', 'N/A')
            industry = info.get('industry', 'N/A')
            if sector != 'N/A' or industry != 'N/A':
                st.markdown(f"**Sector:** {sector} | **Industry:** {industry}")
                
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Current Price", f"${info.get('currentPrice', 'N/A')}")
            market_cap = info.get("marketCap", 0) or 0
            cap_str = f"${market_cap/1e9:.2f}B" if market_cap > 1e9 else f"${market_cap/1e6:.2f}M"
            col2.metric("Market Cap", cap_str)
            col3.metric("P/E Ratio", info.get("trailingPE", "N/A"))
            col4.metric("52W High", f"${info.get('fiftyTwoWeekHigh', 'N/A')}")
        except Exception as e:
            st.error(f"Could not load data for {selected_ticker}. Error: {e}")

    st.markdown("### 🛠️ Deep Dive Tools & AI Reasoning")
    with st.expander("How are the tools calculated?"):
        st.markdown(
            """
* **Intrinsic Value**: Calculated using the classic Graham Number formula: `sqrt(22.5 * EPS * Book Value Per Share)`.
* **RSI (14)**: Calculated using a **14-Day** rolling window of **Daily** closing prices.
* **Technical Trend**: Calculated using a **20-Day** rolling window of **Daily** closing prices.
"""
        )

    st.markdown("Select which tool outputs to generate and feed into the AI for reasoning:")
    col_a, col_b, col_c = st.columns(3)
    use_fund = col_a.checkbox("Fundamentals & Intrinsic Value", value=True)
    use_tech = col_b.checkbox("Technicals (RSI & MA)", value=True)
    use_news = col_c.checkbox("Recent News Feed", value=True)

    st.markdown("LLM settings (for the reasoning block):")
    llm_col1, llm_col2 = st.columns(2)
    llm_provider = llm_col1.selectbox(
        "Provider",
        ["openrouter", "nebius", "openai", "anthropic", "google"],
        index=0,
    )
    default_models = {
        "openrouter": "z-ai/glm-4.5-air:free",
        "nebius": "meta-llama/Llama-3.3-70B-Instruct",
        "openai": "gpt-5.4-mini",
        "anthropic": "claude-3-5-sonnet-latest",
        "google": "gemini-2.5-flash",
    }
    model_name = llm_col2.text_input("Model", value=default_models[llm_provider])

    st.markdown("Timeframe (stocks + crypto):")
    tf_col1, tf_col2 = st.columns(2)
    interval_label = tf_col1.selectbox(
        "Bar interval",
        ["15 min", "30 min", "1 hour", "2 hours", "4 hours", "1 day", "1 week"],
        index=5,
    )
    interval = {
        "15 min": "15m",
        "30 min": "30m",
        "1 hour": "60m",
        "2 hours": "60m",
        "4 hours": "60m",
        "1 day": "1d",
        "1 week": "1wk",
    }[interval_label]
    lookback_mode = tf_col2.radio("Lookback mode", ["Presets", "Custom days"], horizontal=True)
    if lookback_mode == "Presets":
        lookback_options = _lookback_options_for_interval(interval_label)
        period = tf_col2.selectbox("Lookback", lookback_options, index=min(2, len(lookback_options) - 1))
        yf_period = _yf_period_from_label(period)
    else:
        max_days = _max_days_for_interval(interval_label)
        days = int(
            tf_col2.number_input(
                "Lookback (days)",
                min_value=2,
                max_value=max_days,
                value=min(20, max_days),
                step=1,
            )
        )
        yf_period = f"{days}d"

    if interval_label == "4 hours":
        st.caption("4h uses 60m data aggregated into 4-hour bars for broader compatibility.")
    if interval_label == "2 hours":
        st.caption("2h uses 60m data aggregated into 2-hour bars for broader compatibility.")

    if st.button(f"🧠 Run Tools & Generate AI Reasoning for {selected_ticker}", type="primary"):
        _run_deep_dive_reasoning(
            selected_ticker,
            use_fund=use_fund,
            use_tech=use_tech,
            use_news=use_news,
            interval=interval,
            period=yf_period,
            aggregate_bars=(4 if interval_label == "4 hours" else (2 if interval_label == "2 hours" else 1)),
            llm_provider=llm_provider,
            llm_model=model_name,
        )

    st.markdown("### Strategy Modules")
    strategy_module = st.radio(
        "Select Strategy Module to Execute:",
        [
            "🔮 Comprehensive Multi-Agent (Standard)",
            "📈 Momentum Breakout Engine (Beta)",
            "⚡ VWAP Reversion (Beta)",
            "📉 Potential Reversal Engine (Beta)",
        ],
    )
    if strategy_module.startswith("🔮"):
        st.info("Use the **🤖 Agent Execution** tab to run the full multi-agent report.")
    elif strategy_module.startswith("📈"):
        _render_momentum_breakout_beta(selected_ticker)
    elif strategy_module.startswith("⚡"):
        _render_vwap_reversion_beta(selected_ticker)
    else:
        _render_reversal_strategy_beta(selected_ticker)


def _run_deep_dive_reasoning(
    selected_ticker: str,
    *,
    use_fund: bool,
    use_tech: bool,
    use_news: bool,
    interval: str,
    period: str,
    aggregate_bars: int,
    llm_provider: str,
    llm_model: str,
) -> None:
    import yfinance as yf

    stock = yf.Ticker(selected_ticker)
    final_prompt_context = ""
    hist_for_metrics = None
    is_crypto = False
    try:
        info_probe = stock.info or {}
        is_crypto = (info_probe.get("quoteType") == "CRYPTOCURRENCY") or (
            str(info_probe.get("symbol") or "").endswith("-USD")
        )
    except Exception:
        is_crypto = selected_ticker.endswith("-USD")

    if use_fund:
        try:
            info = stock.info or {}
            eps = info.get("trailingEps", 0) or 0
            bvps = info.get("bookValue", 0) or 0
            analyst_target = info.get("targetMeanPrice", 0) or 0

            graham_val = "N/A"
            if eps > 0 and bvps > 0:
                graham_val = f"${(22.5 * eps * bvps) ** 0.5:.2f}"

            fund_text = (
                f"**Graham Intrinsic Value:** {graham_val} | **Analyst Target:** ${analyst_target}\n"
                f"**EPS:** {eps} | **BVPS:** {bvps}"
            )
            st.markdown("#### 💎 Fundamental Tool Output")
            st.info(fund_text)
            final_prompt_context += f"FUNDAMENTALS:\n{fund_text}\n\n"
        except Exception as e:
            st.warning(f"Fundamentals tool failed: {e}")

    if use_tech:
        try:
            hist = stock.history(period=period, interval=interval).dropna()
            if aggregate_bars > 1 and not hist.empty:
                hist = _aggregate_ohlcv(hist, bars=aggregate_bars)
            hist_for_metrics = hist
            if not hist.empty:
                closes = hist["Close"]
                delta = closes.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, 1e-9)
                rsi = 100 - (100 / (1 + rs))
                rsi_val = float(rsi.iloc[-1])

                ma20 = float(closes.rolling(20).mean().iloc[-1])
                last_close = float(closes.iloc[-1])
                trend = "Above 20D MA (Bullish)" if last_close > ma20 else "Below 20D MA (Bearish)"

                tech_text = f"**RSI (14):** {rsi_val:.1f} | **20D MA:** {ma20:.2f} | **Trend:** {trend}"
                st.markdown("#### 🧰 Technical Tool Output")
                st.info(tech_text)
                final_prompt_context += f"TECHNICALS:\n{tech_text}\n\n"
        except Exception as e:
            st.warning(f"Technicals tool failed: {e}")

    # Strategy calculators (momentum/day-trading/options ratios/fake momentum) -> feed into reasoning
    try:
        if hist_for_metrics is None:
            hist_for_metrics = stock.history(period=period, interval=interval).dropna()
            if aggregate_bars > 1 and not hist_for_metrics.empty:
                hist_for_metrics = _aggregate_ohlcv(hist_for_metrics, bars=aggregate_bars)
        if hist_for_metrics is not None and not hist_for_metrics.empty:
            mom = compute_momentum_summary(hist_for_metrics)
            recent_rets = compute_recent_returns(hist_for_metrics, bars=8)
            atr14 = compute_atr14(hist_for_metrics)
            day = compute_day_trading_levels(mom.last_close, atr14)
            bullbear = compute_bull_bear_scores(hist_for_metrics)
            fake = compute_fake_momentum(hist_for_metrics)
            crypto = compute_crypto_summary(hist_for_metrics) if is_crypto else None

            # Options ratio (nearest expiry; uses OI)
            options_text = ""
            if not is_crypto:
                try:
                    expirations = stock.options
                    if expirations:
                        chain = stock.option_chain(expirations[0])
                        call_oi = float(chain.calls["openInterest"].sum())
                        put_oi = float(chain.puts["openInterest"].sum())
                        pc_ratio = (put_oi / call_oi) if call_oi > 0 else None
                        options_text = (
                            f"Nearest expiry: {expirations[0]} | Call OI: {int(call_oi)} | Put OI: {int(put_oi)}"
                            + (f" | Put/Call OI: {pc_ratio:.2f}" if pc_ratio is not None else "")
                        )
                except Exception:
                    options_text = ""

            strategy_lines = [
                f"Momentum returns: 5D={mom.ret_5d}%, 21D={mom.ret_21d}%, 63D={mom.ret_63d}%",
                f"Recent bar returns (%): {recent_rets}" if recent_rets else "",
                f"20D high: {mom.high_20d} | Above 20D high: {mom.above_20d_high}",
                f"Bull score: {bullbear.bull_score} | Bear score: {bullbear.bear_score} | Notes: {', '.join(bullbear.notes[:6])}",
                f"Fake momentum (trap risk): bull_trap={fake.bull_trap_score} ({', '.join(fake.bull_trap_reasons[:3]) or 'n/a'}), bear_trap={fake.bear_trap_score} ({', '.join(fake.bear_trap_reasons[:3]) or 'n/a'})",
            ]
            if crypto is not None:
                strategy_lines.append(
                    f"Crypto summary: 1D={crypto.ret_1d}%, 7D={crypto.ret_7d}%, 30D={crypto.ret_30d}%, vol≈{crypto.vol_7d_annualized}%/yr, volume_spike={crypto.volume_spike}x"
                )
            if day.atr14 is not None:
                strategy_lines.append(
                    f"Day-trading levels (ATR14={day.atr14}): stop1R={day.stop_1r}, stop2R={day.stop_2r}, tp1R={day.takeprofit_1r}, tp2R={day.takeprofit_2r}"
                )
            if options_text:
                strategy_lines.append(f"Options OI ratio: {options_text}")

            strategy_text = "\n".join(f"- {l}" for l in strategy_lines if l)
            st.markdown("#### 🧮 Strategy & Risk Calculators")
            st.info(strategy_text)
            final_prompt_context += f"STRATEGY_CALCULATORS:\n{strategy_text}\n\n"
    except Exception as e:
        st.warning(f"Strategy calculators failed: {e}")

    if use_news:
        try:
            import urllib.request
            import xml.etree.ElementTree as ET
            
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={selected_ticker}&region=US&lang=en-US"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            xml_data = urllib.request.urlopen(req, timeout=5).read()
            root = ET.fromstring(xml_data)
            
            lines = []
            for item in root.findall('.//item')[:6]:
                title = item.find('title').text if item.find('title') is not None else ""
                if title:
                    lines.append(f"- {title}")
                    
            news_text = "\n".join(lines).strip() or "No recent news."

            st.markdown("#### 📰 News Tool Output")
            st.info(news_text)
            final_prompt_context += f"RECENT NEWS:\n{news_text}\n\n"
        except Exception as e:
            st.warning(f"News feed temporarily unavailable: {e}")

    if not final_prompt_context:
        st.warning("No tools were selected for the AI to reason over!")
        return

    prompt = f"""You are an expert quantitative trading agent. You have been provided with the following tool outputs for the stock {selected_ticker}:

{final_prompt_context}

Based strictly on the provided tool outputs, generate a comprehensive trading report.
Your report MUST include:
1. **Core Thesis:** A 3-4 sentence summary of the fundamentals and technicals.
2. **Trading Suitability:** Analyze the data and state whether this stock is good for:
   - Swing Trading (Yes/No & Why)
   - Momentum Trading (Yes/No & Why)
   - Short Term Trading (Yes/No & Why)
   - Long Term Investing (Yes/No & Why)
3. **Price Projection:** Based on the current price and momentum, estimate a realistic price projection. (e.g., "If bullish, it could push to resistance at $X. If bearish, it could drop to support at $Y.")
4. **Final Verdict:** Conclude with a definitive "Final Verdict" (Strong Buy, Buy, Hold, Sell, or Strong Sell).
Format your response cleanly in Markdown.
"""

    try:
        if not _has_llm_credentials(llm_provider):
            st.error(_missing_credentials_message(llm_provider))
            return

        client = create_llm_client(llm_provider, llm_model)
        llm = client.get_llm()
        res = llm.invoke(prompt)
        ai_reasoning = res.content
    except Exception as e:
        ai_reasoning = f"Error generating reasoning: {str(e)}"

    st.markdown("#### 🧠 Final Integrated AI Reasoning")
    st.success(ai_reasoning)


def _aggregate_ohlcv(hist, *, bars: int):
    """
    Aggregate fixed-size bar groups (e.g. 60m -> 4h). Works with yfinance DataFrame.
    """
    import pandas as pd

    if hist is None or hist.empty:
        return hist
    df = hist.copy()
    df = df.reset_index(drop=False)
    df["__grp"] = (df.index // bars).astype(int)
    agg = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
    }
    if "Volume" in df.columns:
        agg["Volume"] = "sum"
    out = df.groupby("__grp", as_index=False).agg(agg)
    # Keep a monotonic index for downstream rolling windows.
    return out


def _lookback_options_for_interval(interval_label: str) -> list[str]:
    # Keep within yfinance typical intraday limits.
    if interval_label in {"15 min", "30 min"}:
        return ["7 days", "30 days", "60 days"]
    if interval_label in {"1 hour", "2 hours", "4 hours"}:
        return ["30 days", "90 days", "6 months", "1 year", "2 years"]
    if interval_label == "1 day":
        return ["30 days", "90 days", "6 months", "1 year", "2 years", "5 years", "Max"]
    return ["6 months", "1 year", "2 years", "5 years", "Max"]


def _yf_period_from_label(label: str) -> str:
    return {
        "7 days": "7d",
        "30 days": "1mo",
        "60 days": "60d",
        "90 days": "3mo",
        "6 months": "6mo",
        "1 year": "1y",
        "2 years": "2y",
        "5 years": "5y",
        "Max": "max",
    }[label]


def _max_days_for_interval(interval_label: str) -> int:
    # Conservative caps to avoid yfinance intraday history failures.
    if interval_label in {"15 min", "30 min"}:
        return 60
    if interval_label in {"1 hour", "2 hours", "4 hours"}:
        return 730  # ~2y
    if interval_label == "1 day":
        return 3650  # ~10y
    return 3650


def _has_llm_credentials(provider: str) -> bool:
    import os

    p = provider.lower()
    if p == "openai":
        return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY") or (st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") else None))
    if p == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY") or (st.secrets.get("ANTHROPIC_API_KEY") if hasattr(st, "secrets") else None))
    if p == "google":
        return bool(os.getenv("GOOGLE_API_KEY") or (st.secrets.get("GOOGLE_API_KEY") if hasattr(st, "secrets") else None))
    if p == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY") or (st.secrets.get("OPENROUTER_API_KEY") if hasattr(st, "secrets") else None))
    if p == "nebius":
        return bool(os.getenv("NEBIUS_API_KEY") or (st.secrets.get("NEBIUS_API_KEY") if hasattr(st, "secrets") else None))
    return True


def _missing_credentials_message(provider: str) -> str:
    p = provider.lower()
    key = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "nebius": "NEBIUS_API_KEY",
    }.get(p, "API_KEY")
    return (
        f"Missing credentials for provider '{provider}'. Add `{key}` in Streamlit Community Cloud -> App -> Settings -> Secrets "
        f"(or set it as an environment variable)."
    )


def _render_momentum_breakout_beta(ticker: str) -> None:
    import yfinance as yf

    st.caption("Beta: 20-day high breakout + ATR stop + volume confirmation.")
    try:
        hist = yf.Ticker(ticker).history(period="6mo", interval="1d").dropna()
        if hist.empty:
            st.warning("No price history available.")
            return
        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]

        last_close = float(close.iloc[-1])
        breakout_level = float(high.rolling(20).max().iloc[-2])
        avg_vol = float(volume.rolling(20).mean().iloc[-2])
        vol_ok = float(volume.iloc[-1]) > 1.5 * avg_vol if avg_vol > 0 else False

        tr = (high - low).to_frame("hl")
        tr["hc"] = (high - close.shift()).abs()
        tr["lc"] = (low - close.shift()).abs()
        atr14 = float(tr.max(axis=1).rolling(14).mean().iloc[-1])
        stop = last_close - 2 * atr14

        st.write(
            {
                "Last Close": round(last_close, 2),
                "20D Breakout Level": round(breakout_level, 2),
                "ATR(14)": round(atr14, 2),
                "Suggested Stop (2x ATR)": round(stop, 2),
                "Volume Confirmation": "Yes" if vol_ok else "No",
            }
        )
        if last_close > breakout_level and vol_ok:
            st.success("Breakout conditions met (price > 20D high and volume elevated).")
        elif last_close > breakout_level:
            st.info("Price is breaking out, but volume confirmation is weak.")
        else:
            st.warning("No breakout yet (price below 20D high).")
    except Exception as e:
        st.warning(f"Momentum breakout module failed: {e}")


def _render_vwap_reversion_beta(ticker: str) -> None:
    import yfinance as yf

    st.caption("Beta: daily VWAP proxy (typical price vs 5D VWAP) for reversion bias.")
    try:
        hist = yf.Ticker(ticker).history(period="10d", interval="1d").dropna()
        if hist.empty:
            st.warning("No price history available.")
            return
        typical = (hist["High"] + hist["Low"] + hist["Close"]) / 3.0
        denom = hist["Volume"].rolling(5).sum().iloc[-1]
        vwap_5d = float((typical * hist["Volume"]).rolling(5).sum().iloc[-1] / denom) if denom else 0.0
        last = float(typical.iloc[-1])
        deviation = (last - vwap_5d) / vwap_5d * 100 if vwap_5d else 0.0

        st.write(
            {"Typical Price (Last)": round(last, 2), "5D VWAP": round(vwap_5d, 2), "Deviation %": round(deviation, 2)}
        )
        if deviation <= -2.0:
            st.success("Mean reversion long bias (typical price materially below VWAP).")
        elif deviation >= 2.0:
            st.info("Mean reversion short/avoid chase (typical price materially above VWAP).")
        else:
            st.warning("No strong reversion signal (near VWAP).")
    except Exception as e:
        st.warning(f"VWAP reversion module failed: {e}")


def _render_agent_execution() -> None:
    st.title("📈 TradingAgents AI Simulation")
    st.markdown("Run specific tickers through the multi-agent LLM framework.")

    with st.sidebar:
        st.header("Trade Settings")
        default_tick = st.session_state.get("target_ticker", "NVDA")
        ticker = st.text_input("Stock Ticker", value=default_tick).upper()
        trade_date = st.date_input("Analysis Date", value=datetime.date.today())

        st.header("LLM Settings")
        default_models = {
            "nebius": "meta-llama/Llama-3.3-70B-Instruct",
            "google": "gemini-2.5-flash",
            "openrouter": "z-ai/glm-4.5-air:free",
            "openai": "gpt-5.4-mini",
            "anthropic": "claude-3-5-sonnet-latest",
        }

        llm_provider = st.selectbox("Provider", list(default_models.keys()), index=0)
        model_name = st.text_input("Model Name", value=default_models[llm_provider])

        col1, col2 = st.columns(2)
        with col1:
            run_button = st.button("🚀 Start", type="primary")
        with col2:
            if st.button("🛑 Stop", type="secondary"):
                st.stop()

    if not run_button:
        return
    if not ticker:
        st.error("Please enter a valid stock ticker.")
        return

    st.subheader("Live Agent Activity")
    log_placeholder = st.empty()

    with st.spinner(f"Running multi-agent simulation for {ticker}... (This takes a few minutes)"):
        redirector = StreamlitRedirect(log_placeholder)
        old_stdout = sys.stdout
        sys.stdout = redirector

        try:
            config = DEFAULT_CONFIG.copy()
            config["llm_provider"] = llm_provider
            config["deep_think_llm"] = model_name
            config["quick_think_llm"] = model_name
            config["max_debate_rounds"] = 1

            ta = TradingAgentsGraph(debug=True, config=config)
            date_str = trade_date.strftime("%Y-%m-%d")
            final_state, signal = ta.propagate(ticker, date_str)
        except Exception as e:
            sys.stdout = old_stdout
            st.error(f"An error occurred: {str(e)}")
            st.stop()
            return
        finally:
            sys.stdout = old_stdout

        log_placeholder.empty()
        st.success("Simulation Complete!")

        tabs = st.tabs(["💡 Final Decision", "📊 Analyst Reports", "📝 Trader Plan", "⚖️ Debates", "📜 Full Execution Logs"])

        with tabs[0]:
            st.subheader(f"Final Signal: {signal}")
            st.markdown("### Portfolio Manager's Decision")
            st.write(final_state.get("final_trade_decision", "No decision output."))

        with tabs[1]:
            col1, col2 = st.columns(2)
            with col1:
                with st.expander("📈 Market/Technical Report", expanded=True):
                    st.write(final_state.get("market_report", "N/A"))
                with st.expander("📰 News Report", expanded=False):
                    st.write(final_state.get("news_report", "N/A"))
            with col2:
                with st.expander("🏢 Fundamentals Report", expanded=True):
                    st.write(final_state.get("fundamentals_report", "N/A"))
                with st.expander("💬 Sentiment Report", expanded=False):
                    st.write(final_state.get("sentiment_report", "N/A"))

        with tabs[2]:
            st.markdown("### Trader's Investment Plan")
            plan = final_state.get("trader_investment_plan") or final_state.get("investment_plan", "N/A")
            st.write(plan)

        with tabs[3]:
            st.markdown("### Investment Debate State")
            debate = final_state.get("investment_debate_state", {})
            st.write("**Judge Decision:**")
            st.write(debate.get("judge_decision", "N/A"))

        with tabs[4]:
            st.markdown("### Execution Logs")
            st.code(redirector.content, language="text")

def _render_reversal_strategy_beta(ticker: str) -> None:
    import yfinance as yf

    st.caption("Beta: RSI extremes + MACD Crossover for potential trend reversal detection.")
    try:
        hist = yf.Ticker(ticker).history(period="3mo", interval="1d").dropna()
        if hist.empty:
            st.warning("No price history available.")
            return
        
        close = hist["Close"]
        
        # RSI 14
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        last_rsi = float(rsi.iloc[-1])
        
        # MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist_macd = macd - signal
        
        macd_crossover_bull = float(hist_macd.iloc[-2]) < 0 and float(hist_macd.iloc[-1]) > 0
        macd_crossover_bear = float(hist_macd.iloc[-2]) > 0 and float(hist_macd.iloc[-1]) < 0
        
        st.write({
            "Current RSI (14)": round(last_rsi, 2),
            "Oversold (<30)": "Yes" if last_rsi < 30 else "No",
            "Overbought (>70)": "Yes" if last_rsi > 70 else "No",
            "MACD Bull Crossover": "Yes" if macd_crossover_bull else "No",
            "MACD Bear Crossover": "Yes" if macd_crossover_bear else "No",
        })
        
        if last_rsi < 35 and macd_crossover_bull:
            st.success("🔥 Bullish Reversal Detected: Price is oversold and MACD is crossing up.")
        elif last_rsi > 65 and macd_crossover_bear:
            st.error("🩸 Bearish Reversal Detected: Price is overbought and MACD is crossing down.")
        elif last_rsi < 30:
            st.info("Stock is oversold. Watch for a bullish MACD crossover to confirm reversal.")
        elif last_rsi > 70:
            st.warning("Stock is overbought. Watch for a bearish MACD crossover to confirm reversal.")
        else:
            st.write("No extreme reversal signals at the moment. Trend is normal.")
            
    except Exception as e:
        st.warning(f"Reversal module failed: {e}")

def _run_agentic_earnings_analysis(df, provider: str):
    if not _has_llm_credentials(provider):
        st.error(_missing_credentials_message(provider))
        return

    tickers = df["Ticker"].head(5).tolist()
    if not tickers:
        st.warning("No tickers to analyze.")
        return

    st.info(f"Gathering data for {', '.join(tickers)}...")
    
    context = ""
    for tick in tickers:
        try:
            from tradingagents.market_data.fundamentals import get_stock_info
            info = get_stock_info(tick)
            context += f"TICKER: {tick}\n"
            context += f"Sector: {info.get('sector', 'N/A')} | Market Cap: {info.get('marketCap', 'N/A')}\n"
            context += f"Forward PE: {info.get('forwardPE', 'N/A')} | Current Price: {info.get('currentPrice', 'N/A')}\n"
            
            import urllib.request
            import xml.etree.ElementTree as ET
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={tick}&region=US&lang=en-US"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            xml_data = urllib.request.urlopen(req, timeout=3).read()
            root = ET.fromstring(xml_data)
            news_lines = []
            for item in root.findall('.//item')[:3]:
                title = item.find('title').text if item.find('title') is not None else ""
                if title: news_lines.append(f"- {title}")
            context += "RECENT NEWS:\n" + "\n".join(news_lines) + "\n\n"
        except Exception:
            context += f"TICKER: {tick}\nData temporarily unavailable.\n\n"
            
    prompt = f"""You are an expert earnings analyst AI. Review the fundamental data and latest news for the following companies reporting earnings:
    
{context}

Your task is to segregate these stocks into two clear categories:
1. 🟢 BULLISH (Strong fundamentals, positive news sentiment)
2. 🔴 BEARISH (Weak fundamentals, negative news sentiment or overvalued)

Give a 1-sentence reason for each stock's categorization based strictly on the provided data.
Format your output cleanly in Markdown.
"""
    with st.spinner("🧠 AI is analyzing earnings data and segregating stocks..."):
        try:
            from tradingagents.llm_clients import create_llm_client
            # Basic model selection for the agent
            model_name = "z-ai/glm-4.5-air:free" if provider == "openrouter" else ""
            client = create_llm_client(provider, model_name)
            res = client.get_llm().invoke(prompt)
            st.markdown("### 📊 Agentic Earnings Report")
            st.success(res.content)
        except Exception as e:
            st.error(f"Analysis failed: {e}")
