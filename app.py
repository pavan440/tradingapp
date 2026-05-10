import streamlit as st
import datetime
import os
import sys
from dotenv import load_dotenv

# Must be the first Streamlit command
st.set_page_config(page_title="TradingAgents AI", page_icon="📈", layout="wide")

load_dotenv(override=True)

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

import yfinance as yf

try:
    from finvizfinance.screener.overview import Overview
    from finvizfinance.group.performance import Performance
except ImportError:
    st.error("Please install finvizfinance using: pip install finvizfinance")

class StreamlitRedirect:
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.content = ""

    def write(self, text):
        self.content += text
        # Keep only the last 5000 characters to prevent lag
        if len(self.content) > 5000:
            self.content = "..." + self.content[-5000:]
        self.placeholder.code(self.content, language="text")

    def flush(self):
        pass

@st.cache_data(ttl=3600)
def get_sector_performance():
    return Performance().screener_view(group='Sector')

@st.cache_data(ttl=3600)
def get_stock_info(ticker):
    return yf.Ticker(ticker).info

@st.cache_data(ttl=300)
def get_crypto_performance():
    try:
        from finvizfinance.crypto import Crypto
        return Crypto().performance()
    except Exception:
        return None

def check_dataframe_click(event, df):
    if getattr(event, "selection", None) and getattr(event.selection, "rows", None):
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            st.session_state['target_ticker'] = df.iloc[idx]['Ticker']

@st.cache_data(ttl=300)
def get_market_indices():
    import yfinance as yf
    tickers = yf.Tickers("SPY QQQ DIA")
    data = []
    for t in ["SPY", "QQQ", "DIA"]:
        try:
            hist = tickers.tickers[t].history(period="2d")
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current = hist['Close'].iloc[-1]
                pct_change = ((current - prev_close) / prev_close) * 100
                data.append({"Ticker": t, "Price": current, "Change": pct_change})
        except:
            pass
    return data

@st.cache_data(ttl=300)
def get_sp500_top_gainers():
    import pandas as pd
    from finvizfinance.screener.overview import Overview
    try:
        foverview = Overview()
        foverview.set_filter(signal='Top Gainers', filters_dict={'Index': 'S&P 500'})
        df = foverview.screener_view(limit=10, sleep_sec=0)
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_options_flow():
    import pandas as pd
    from finvizfinance.screener.overview import Overview
    foverview = Overview()
    foverview.set_filter(signal='Most Active', filters_dict={'Option/Short': 'Optionable'})
    try:
        df = foverview.screener_view(limit=25, sleep_sec=0)
    except:
        return pd.DataFrame()
        
    results = []
    if df is not None and not df.empty:
        tickers = df['Ticker'].tolist()
        for t in tickers:
            try:
                stock = yf.Ticker(t)
                expirations = stock.options
                if expirations:
                    # Nearest expiry
                    chain = stock.option_chain(expirations[0])
                    call_oi = chain.calls['openInterest'].sum()
                    put_oi = chain.puts['openInterest'].sum()
                    
                    results.append({
                        'Ticker': t,
                        'Call OI': int(call_oi),
                        'Put OI': int(put_oi),
                        'P/C Ratio': round(put_oi / call_oi, 2) if call_oi > 0 else 0
                    })
            except Exception:
                pass
    return pd.DataFrame(results)

# Sidebar Navigation
page = st.sidebar.radio("Navigation", ["🔍 Market Scanner", "🤖 Agent Execution"])

if page == "🔍 Market Scanner":
    if 'all_tickers' not in st.session_state:
        st.session_state['all_tickers'] = set(["NVDA", "AAPL", "MSFT", "TSLA", "AMD", "SPY", "QQQ"])
        
    st.title("🔍 Global Market Scanner")
    st.markdown("Filter the market for trending plays, penny stocks, and earnings momentum.")
    
    st.subheader("📈 Major Indices")
    indices = get_market_indices()
    if indices:
        for idx in indices:
            st.session_state['all_tickers'].add(idx["Ticker"])
        cols = st.columns(len(indices))
        for i, col in enumerate(cols):
            col.metric(indices[i]["Ticker"], f"${indices[i]['Price']:.2f}", f"{indices[i]['Change']:.2f}%")
    st.markdown("---")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📊 Sector Performance Graph")
        try:
            perf_df = get_sector_performance()
            # Bar chart of sectors using the 'Change' column (already float)
            st.bar_chart(perf_df.set_index('Name')['Change'])
        except Exception as e:
            st.warning(f"Could not load sector performance: {e}")
            
    with c2:
        st.subheader("🚀 Top S&P 500 Movers (Price Change)")
        try:
            sp500_df = get_sp500_top_gainers()
            if not sp500_df.empty:
                st.session_state['all_tickers'].update(sp500_df['Ticker'].tolist())
                # Sort descending for better chart visual
                sp500_df = sp500_df.sort_values('Change', ascending=False)
                st.bar_chart(sp500_df.set_index('Ticker')['Change'])
        except Exception as e:
            st.warning(f"Could not load S&P 500 movers: {e}")
        
    st.markdown("---")
    st.subheader("🪙 Crypto Overview")
    try:
        crypto_df = get_crypto_performance()
        if crypto_df is not None and not crypto_df.empty:
            # Finviz crypto returns floats directly, no need to strip '%'
            top_gainers = crypto_df.nlargest(15, 'Perf Day')
            top_losers = crypto_df.nsmallest(15, 'Perf Day')
            
            # Format the output for readability
            top_gainers['Perf Day'] = (top_gainers['Perf Day'] * 100).round(2).astype(str) + '%'
            top_losers['Perf Day'] = (top_losers['Perf Day'] * 100).round(2).astype(str) + '%'
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Top Gainers (24H)**")
                evt1 = st.dataframe(top_gainers[['Ticker', 'Price', 'Perf Day']], hide_index=True, on_select="rerun", selection_mode="single-row")
                check_dataframe_click(evt1, top_gainers)
                st.session_state['all_tickers'].update(top_gainers['Ticker'].tolist())
            with c2:
                st.markdown("**Top Losers (24H)**")
                evt2 = st.dataframe(top_losers[['Ticker', 'Price', 'Perf Day']], hide_index=True, on_select="rerun", selection_mode="single-row")
                check_dataframe_click(evt2, top_losers)
                st.session_state['all_tickers'].update(top_losers['Ticker'].tolist())
    except Exception as e:
        st.warning(f"Could not load crypto overview: {e}")

    st.markdown("---")
    st.subheader("📊 Options Flow Scanner")
    st.markdown("Scanning the most active optionable stocks to track Open Interest on Calls and Puts.")
    
    if st.button("🚀 Scan Call/Put Open Interest", type="primary"):
        with st.spinner("Analyzing options chains for the most active stocks... (This takes 10-15 seconds)"):
            flow_df = get_options_flow()
            if not flow_df.empty:
                st.session_state['options_flow_df'] = flow_df
                st.session_state['all_tickers'].update(flow_df['Ticker'].tolist())
            else:
                st.warning("Could not retrieve options data. The market may be closed or Yahoo Finance is rate-limiting.")
                
    if 'options_flow_df' in st.session_state and not st.session_state['options_flow_df'].empty:
        flow_df = st.session_state['options_flow_df']
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🔥 Highest Call Interest**")
            call_heavy = flow_df.nlargest(10, 'Call OI')
            evt3 = st.dataframe(call_heavy[['Ticker', 'Call OI', 'P/C Ratio']], hide_index=True, on_select="rerun", selection_mode="single-row")
            check_dataframe_click(evt3, call_heavy)
            
        with col2:
            st.markdown("**🩸 Highest Put Interest**")
            put_heavy = flow_df.nlargest(10, 'Put OI')
            evt4 = st.dataframe(put_heavy[['Ticker', 'Put OI', 'P/C Ratio']], hide_index=True, on_select="rerun", selection_mode="single-row")
            check_dataframe_click(evt4, put_heavy)

    st.markdown("---")
    st.subheader("🎯 Stock Screener")
    
    scan_type = st.selectbox("Select Scan Strategy", [
        "Penny Stock Catalyst Runners (Under $10, High Vol)",
        "Large/Mid Cap Momentum (Unusual Volume)",
        "Optionable Top Losers (High Volatility)",
        "Earnings Today",
        "Earnings Tomorrow",
        "Earnings This Week"
    ])
    
    if st.button("🚀 Run Scanner", type="primary"):
        with st.spinner("Scanning market data..."):
            foverview = Overview()
            try:
                if scan_type == "Penny Stock Catalyst Runners (Under $10, High Vol)":
                    filters_dict = {'Price': 'Under $10', 'Relative Volume': 'Over 2'}
                    foverview.set_filter(signal='Top Gainers', filters_dict=filters_dict)
                    df = foverview.screener_view(limit=50, sleep_sec=0)
                
                elif scan_type == "Large/Mid Cap Momentum (Unusual Volume)":
                    filters_dict = {'Market Cap.': '+Mid (over $2bln)', 'Relative Volume': 'Over 2'}
                    foverview.set_filter(signal='Unusual Volume', filters_dict=filters_dict)
                    df = foverview.screener_view(limit=50, sleep_sec=0)
                    
                elif scan_type == "Optionable Top Losers (High Volatility)":
                    filters_dict = {'Option/Short': 'Optionable', 'Relative Volume': 'Over 2'}
                    foverview.set_filter(signal='Top Losers', filters_dict=filters_dict)
                    df = foverview.screener_view(limit=50, sleep_sec=0)
                    
                elif scan_type == "Earnings Today":
                    filters_dict = {'Earnings Date': 'Today'}
                    foverview.set_filter(filters_dict=filters_dict)
                    df = foverview.screener_view(limit=50, sleep_sec=0)
                    
                elif scan_type == "Earnings Tomorrow":
                    filters_dict = {'Earnings Date': 'Tomorrow'}
                    foverview.set_filter(filters_dict=filters_dict)
                    df = foverview.screener_view(limit=50, sleep_sec=0)
                    
                elif scan_type == "Earnings This Week":
                    filters_dict = {'Earnings Date': 'This Week', 'Market Cap.': '+Small (over $300mln)'}
                    foverview.set_filter(filters_dict=filters_dict)
                    df = foverview.screener_view(limit=50, sleep_sec=0)

                if df is not None and not df.empty:
                    st.success(f"Found {len(df)} stocks matching your criteria!")
                    evt5 = st.dataframe(df, on_select="rerun", selection_mode="single-row")
                    check_dataframe_click(evt5, df)
                    st.session_state['scanned_df'] = df
                    st.session_state['all_tickers'].update(df['Ticker'].tolist())
                else:
                    st.warning("No stocks found matching these criteria at the moment.")
                    st.session_state['scanned_df'] = None
            except Exception as e:
                st.error(f"Scanner Error: {str(e)}")

    # Keep the table visible if it exists in memory, even if the button isn't actively clicked
    elif 'scanned_df' in st.session_state and st.session_state['scanned_df'] is not None:
        st.success(f"Found {len(st.session_state['scanned_df'])} stocks matching your criteria!")
        evt6 = st.dataframe(st.session_state['scanned_df'], on_select="rerun", selection_mode="single-row")
        check_dataframe_click(evt6, st.session_state['scanned_df'])

    st.markdown("---")
    st.subheader("🕵️ Deep Dive & Strategy Setup")
    
    # Text input allows them to type ANY ticker, or use the gathered list
    ticker_list = sorted(list(st.session_state.get('all_tickers', ["NVDA"])))
    
    # Check if a ticker was selected via click
    default_tick = st.session_state.get('target_ticker', ticker_list[0] if ticker_list else "NVDA")
    if default_tick not in ticker_list:
        ticker_list.append(default_tick)
        ticker_list = sorted(ticker_list)
        
    try:
        default_index = ticker_list.index(default_tick)
    except:
        default_index = 0
        
    selected_ticker = st.selectbox("Select ANY stock you see above (or click a table row above) to analyze:", ticker_list, index=default_index)
    
    if selected_ticker:
        st.session_state['target_ticker'] = selected_ticker
        with st.spinner(f"Fetching quick snapshot for {selected_ticker}..."):
            try:
                info = get_stock_info(selected_ticker)
                
                st.markdown(f"**Quick Fundamental & Technical Snapshot for {selected_ticker}**")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Current Price", f"${info.get('currentPrice', 'N/A')}")
                
                market_cap = info.get('marketCap', 0)
                cap_str = f"${market_cap/1e9:.2f}B" if market_cap > 1e9 else f"${market_cap/1e6:.2f}M"
                col2.metric("Market Cap", cap_str)
                
                col3.metric("P/E Ratio", info.get('trailingPE', 'N/A'))
                col4.metric("52W High", f"${info.get('fiftyTwoWeekHigh', 'N/A')}")
            except Exception as e:
                st.error(f"Could not load data for {selected_ticker}. It may be an unsupported crypto or index. Error: {e}")
            
            st.markdown("### 🛠️ Deep Dive Tools & AI Reasoning")
            
            with st.expander("How are the tools calculated?"):
                st.markdown("""
                * **Intrinsic Value**: Calculated using the classic Graham Number formula: `sqrt(22.5 * EPS * Book Value Per Share)`.
                * **RSI (14)**: Calculated using a **14-Day** rolling window of **Daily** closing prices.
                * **Technical Trend**: Calculated using a **20-Day** rolling window of **Daily** closing prices.
                """)
                
            st.markdown("Select which tool outputs to generate and feed into the AI for reasoning:")
            col_a, col_b, col_c = st.columns(3)
            use_fund = col_a.checkbox("Fundamentals & Intrinsic Value", value=True)
            use_tech = col_b.checkbox("Technicals (Daily RSI & MA)", value=True)
            use_news = col_c.checkbox("Recent News Feed", value=True)
            
            if st.button(f"🧠 Run Tools & Generate AI Reasoning for {selected_ticker}", type="primary"):
                with st.spinner("Calculating tools and generating reasoning..."):
                    import yfinance as yf
                    from tradingagents.llm_clients.factory import create_llm_client
                    
                    stock = yf.Ticker(selected_ticker)
                    final_prompt_context = ""
                    
                    # 1. Fundamental Tool
                    if use_fund:
                        try:
                            info = stock.info
                            eps = info.get('trailingEps', 0)
                            bvps = info.get('bookValue', 0)
                            analyst_target = info.get('targetMeanPrice', 0)
                            
                            graham_val = "N/A"
                            if eps and bvps and eps > 0 and bvps > 0:
                                graham_val = f"${(22.5 * eps * bvps) ** 0.5:.2f}"
                                
                            fund_text = f"**Graham Intrinsic Value:** {graham_val} | **Analyst Target:** ${analyst_target}\n**EPS:** {eps} | **BVPS:** {bvps}"
                            st.markdown("#### 💎 Fundamental Tool Output")
                            st.info(fund_text)
                            final_prompt_context += f"FUNDAMENTAL DATA:\n{fund_text}\n\n"
                        except:
                            st.warning("Fundamental data unavailable.")
                    
                    # 2. Technical Tool
                    if use_tech:
                        try:
                            hist = stock.history(period="3mo")
                            if not hist.empty and len(hist) >= 20:
                                close_prices = hist['Close']
                                ma20 = close_prices.rolling(window=20).mean().iloc[-1]
                                current = close_prices.iloc[-1]
                                
                                delta = close_prices.diff()
                                gain = delta.where(delta > 0, 0).rolling(window=14).mean().iloc[-1]
                                loss = -delta.where(delta < 0, 0).rolling(window=14).mean().iloc[-1]
                                rs = gain / loss if loss > 0 else 0
                                rsi = 100 - (100 / (1 + rs)) if loss > 0 else 100
                                
                                trend = "Bullish (Price > MA)" if current > ma20 else "Bearish (Price < MA)"
                                rsi_state = "Oversold" if rsi < 30 else ("Overbought" if rsi > 70 else "Neutral")
                                
                                tech_text = f"**Current Price:** ${current:.2f}\n**20-Day Daily MA:** ${ma20:.2f} ({trend})\n**14-Day Daily RSI:** {rsi:.2f} ({rsi_state})"
                                st.markdown("#### 📊 Technical Tool Output")
                                st.info(tech_text)
                                final_prompt_context += f"TECHNICAL DATA:\n{tech_text}\n\n"
                            else:
                                st.warning("Not enough data for Technical Tool.")
                        except:
                            st.warning("Technical data unavailable.")
                            
                    # 3. News Tool
                    if use_news:
                        try:
                            news = stock.news
                            news_text = ""
                            if news:
                                for n in news[:5]:
                                    if 'content' in n and 'title' in n['content']:
                                        news_text += f"- {n['content']['title']}\n"
                            if not news_text:
                                news_text = "No recent news."
                                
                            st.markdown("#### 📰 News Tool Output")
                            st.info(news_text)
                            final_prompt_context += f"RECENT NEWS:\n{news_text}\n\n"
                        except:
                            st.warning("News feed temporarily unavailable.")
                            
                    # 4. LLM Reasoning Integration
                    if final_prompt_context:
                        prompt = f"""
                        You are an expert quantitative trading agent. You have been provided with the following tool outputs for the stock {selected_ticker}:
                        
                        {final_prompt_context}
                        
                        Based strictly on the provided tool outputs, generate a highly cohesive trading reasoning thesis. 
                        Conclude with a definitive "Final Verdict" (Strong Buy, Buy, Hold, Sell, or Strong Sell).
                        Keep your response to a punchy 3-4 sentence paragraph, plus the final verdict. Format in Markdown.
                        """
                        
                        try:
                            client = create_llm_client('nebius', 'meta-llama/Llama-3.3-70B-Instruct')
                            llm = client.get_llm()
                            res = llm.invoke(prompt)
                            ai_reasoning = res.content
                        except Exception as e:
                            ai_reasoning = f"Error generating reasoning: {str(e)}"
                            
                        st.markdown("#### 🧠 Final Integrated AI Reasoning")
                        st.success(ai_reasoning)
                    else:
                        st.warning("No tools were selected for the AI to reason over!")
                    
            st.markdown("### Strategic Tools")
            strategy = st.radio("Select Strategy Module to Execute:", [
                "🔮 Comprehensive Multi-Agent (Standard Phase 3)",
                "📈 Momentum Breakout Engine (Coming in Phase 3 Update)",
                "📊 Options Flow & Greeks (Coming in Phase 3 Update)",
                "⚡ Day Trading VWAP Reversion (Coming in Phase 3 Update)"
            ])
            
            if strategy.startswith("🔮"):
                st.info("Head over to the **🤖 Agent Execution** tab on the left sidebar to run the full AI Analyst report on this stock!")
            else:
                st.warning("This strategy module is actively being built on our Architecture Roadmap!")

elif page == "🤖 Agent Execution":
    st.title("📈 TradingAgents AI Simulation")
    st.markdown("Run specific tickers through the multi-agent LLM framework.")

    with st.sidebar:
        st.header("Trade Settings")
        default_tick = st.session_state.get('target_ticker', "NVDA")
        ticker = st.text_input("Stock Ticker", value=default_tick).upper()
        trade_date = st.date_input("Analysis Date", value=datetime.date(2024, 5, 10))
        
        st.header("LLM Settings")
        
        # Dictionary of default models for each provider
        default_models = {
            "nebius": "meta-llama/Llama-3.3-70B-Instruct",
            "google": "gemini-2.5-flash",
            "openrouter": "z-ai/glm-4.5-air:free",
            "openai": "gpt-5.4-mini",
            "anthropic": "claude-3-5-sonnet-latest"
        }
        
        llm_provider = st.selectbox("Provider", list(default_models.keys()), index=0)
        
        # Dynamically update the default model when the provider changes
        model_name = st.text_input("Model Name", value=default_models[llm_provider])
        
        col1, col2 = st.columns(2)
        with col1:
            run_button = st.button("🚀 Start", type="primary")
        with col2:
            if st.button("🛑 Stop", type="secondary"):
                st.stop()

    if run_button:
        if not ticker:
            st.error("Please enter a valid stock ticker.")
        else:
            # Setup an area for live logs above the tabs
            st.subheader("Live Agent Activity")
            log_placeholder = st.empty()
            
            with st.spinner(f"Running multi-agent simulation for {ticker}... (This takes a few minutes)"):
                redirector = StreamlitRedirect(log_placeholder)
                old_stdout = sys.stdout
                sys.stdout = redirector
                
                try:
                    # Setup Config
                    config = DEFAULT_CONFIG.copy()
                    config["llm_provider"] = llm_provider
                    config["deep_think_llm"] = model_name
                    config["quick_think_llm"] = model_name
                    config["max_debate_rounds"] = 1
                    
                    # Initialize Graph with debug=True to get logs printed
                    ta = TradingAgentsGraph(debug=True, config=config)
                    
                    # Run Simulation
                    date_str = trade_date.strftime("%Y-%m-%d")
                    final_state, signal = ta.propagate(ticker, date_str)
                    
                except Exception as e:
                    sys.stdout = old_stdout
                    st.error(f"An error occurred: {str(e)}")
                    st.stop()
                finally:
                    sys.stdout = old_stdout
                    
                log_placeholder.empty() # Clear live logs once done
                st.success("Simulation Complete!")
                
                # Create tabs for outputs
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
