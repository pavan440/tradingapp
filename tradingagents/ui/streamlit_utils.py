from __future__ import annotations

import streamlit as st


class StreamlitRedirect:
    def __init__(self, placeholder: "st.delta_generator.DeltaGenerator") -> None:
        self.placeholder = placeholder
        self.content = ""

    def write(self, text: str) -> None:
        self.content += text
        if len(self.content) > 5000:
            self.content = "..." + self.content[-5000:]
        self.placeholder.code(self.content, language="text")

    def flush(self) -> None:
        pass


def check_dataframe_click(event, df) -> None:
    if getattr(event, "selection", None) and getattr(event.selection, "rows", None):
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            st.session_state["target_ticker"] = df.iloc[idx]["Ticker"]

