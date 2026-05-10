import streamlit as st

# Must be the very first Streamlit command
st.set_page_config(page_title="TradingAgents AI", page_icon="📈", layout="wide")

from tradingagents.ui.auth import auth_ui
from tradingagents.ui.app_main import main

if auth_ui():
    main()
