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


def main() -> None:
    st.set_page_config(page_title="TradingAgents AI", page_icon="📈", layout="wide")
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

    st.markdown("---")
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
    use_tech = col_b.checkbox("Technicals (Daily RSI & MA)", value=True)
    use_news = col_c.checkbox("Recent News Feed", value=True)

    if st.button(f"🧠 Run Tools & Generate AI Reasoning for {selected_ticker}", type="primary"):
        _run_deep_dive_reasoning(selected_ticker, use_fund=use_fund, use_tech=use_tech, use_news=use_news)

    st.markdown("### Strategy Modules")
    strategy_module = st.radio(
        "Select Strategy Module to Execute:",
        [
            "🔮 Comprehensive Multi-Agent (Standard)",
            "📈 Momentum Breakout Engine (Beta)",
            "⚡ VWAP Reversion (Beta)",
        ],
    )
    if strategy_module.startswith("🔮"):
        st.info("Use the **🤖 Agent Execution** tab to run the full multi-agent report.")
    elif strategy_module.startswith("📈"):
        _render_momentum_breakout_beta(selected_ticker)
    else:
        _render_vwap_reversion_beta(selected_ticker)


def _run_deep_dive_reasoning(selected_ticker: str, *, use_fund: bool, use_tech: bool, use_news: bool) -> None:
    import yfinance as yf

    stock = yf.Ticker(selected_ticker)
    final_prompt_context = ""

    if use_fund:
        try:
            info = stock.info
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
            hist = stock.history(period="6mo", interval="1d").dropna()
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

    if use_news:
        try:
            news = stock.news or []
            lines = []
            for item in news[:6]:
                title = item.get("title") or ""
                publisher = item.get("publisher") or ""
                lines.append(f"- {title} ({publisher})")
            news_text = "\n".join(lines).strip() or "No recent news."

            st.markdown("#### 📰 News Tool Output")
            st.info(news_text)
            final_prompt_context += f"RECENT NEWS:\n{news_text}\n\n"
        except Exception:
            st.warning("News feed temporarily unavailable.")

    if not final_prompt_context:
        st.warning("No tools were selected for the AI to reason over!")
        return

    prompt = f"""You are an expert quantitative trading agent. You have been provided with the following tool outputs for the stock {selected_ticker}:

{final_prompt_context}

Based strictly on the provided tool outputs, generate a cohesive trading thesis.
Conclude with a definitive "Final Verdict" (Strong Buy, Buy, Hold, Sell, or Strong Sell).
Keep your response to 3-4 punchy sentences, plus the final verdict. Format in Markdown.
"""

    try:
        client = create_llm_client("nebius", "meta-llama/Llama-3.3-70B-Instruct")
        llm = client.get_llm()
        res = llm.invoke(prompt)
        ai_reasoning = res.content
    except Exception as e:
        ai_reasoning = f"Error generating reasoning: {str(e)}"

    st.markdown("#### 🧠 Final Integrated AI Reasoning")
    st.success(ai_reasoning)


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

