import streamlit as st


def get_theme():
    light = st.session_state.get("light_mode", False)
    if light:
        return {
            "card_bg": "#ffffff",
            "card_border": "#e5e7ee",
            "header_bg": "#f5f6fa",
            "funds_bg": "linear-gradient(135deg,#eaf3ff 0%,#d6e7f8 100%)",
            "text_primary": "#1a1a2e",
            "text_secondary": "#3d3d52",
            "text_muted": "#7a7a8c",
            "hover": "#f0f2f7",
            "green": "#1ba572",
            "red": "#e34a3a",
            "exch_bg": "#eceef4",
            "exch_text": "#555",
            "funds_caption": "#5a5a72",
        }
    return {
        "card_bg": "#1e1e30",
        "card_border": "#2a2a4a",
        "header_bg": "#16162a",
        "funds_bg": "linear-gradient(135deg,#1a1a2e 0%,#16213e 100%)",
        "text_primary": "#ffffff",
        "text_secondary": "#cccccc",
        "text_muted": "#8888aa",
        "hover": "#26263d",
        "green": "#22a06b",
        "red": "#eb5b3c",
        "exch_bg": "#2a2a4a",
        "exch_text": "#aaaaaa",
        "funds_caption": "#8888aa",
    }
