import os
import threading
import streamlit as st

from auth.kotak_client import get_redis, get_kotak, load_stocks_nse, load_stocks_bse
from data.sync import sync_cnc, sync_mtf, sync_fo_positions, background_sync
from ui.dashboard import page_dashboard
from ui.place_order_ui import page_place_order
from ui.order_history import page_order_history, page_gtt
from fo.fo_ui_helper import render_fo_page
from config import REDIS_CNC_LAST_SYNC


def main():
    st.set_page_config(page_title="Portfolio Manager", page_icon="📊", layout="wide")
    st.markdown(
        """
        <style>
        #MainMenu { visibility: hidden !important; }
        header[data-testid="stHeader"] { height: 0 !important; min-height: 0 !important; }
        footer { visibility: hidden !important; }
        [data-testid="stToolbar"] { display: none !important; }
        .block-container { padding-top: 0.6rem !important; padding-bottom: 1.2rem !important; }
        div[data-testid="stButton"] button[data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, #1ba572, #17916a) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 13px !important;
            height: 38px !important;
        }
        div[data-testid="stVerticalBlock"] > div:first-child { padding-top: 0 !important; }
        .stRadio > div { gap: 0.3rem !important; }
        [data-testid="stHorizontalBlock"] { align-items: center !important; }
        div[data-testid="stHorizontalBlock"] { gap: 0.6rem; }
        hr { margin: 0.6rem 0 !important; }
        .holdings-row:hover { background:#f0f2f5 !important; }
        div[data-testid="stButton"] button[kind="secondary"] {
            font-size: 11px !important; padding: 2px 4px !important;
            min-height: 28px !important;
        }
        [data-testid="column"] button[kind="secondary"]:has(p:contains("B")) {
            background-color: #e8f8f0 !important;
            border-color: #1ba572 !important;
            color: #1ba572 !important;
            font-weight: 700 !important;
        }
        [data-testid="column"] button[kind="secondary"]:has(p:contains("S")) {
            background-color: #fff0ef !important;
            border-color: #e34a3a !important;
            color: #e34a3a !important;
            font-weight: 700 !important;
        }
        div[data-testid="stSelectbox"] > div { min-height: 36px !important; font-size: 13px !important; }
        div[data-testid="stSelectbox"] > label { display: none !important; }
        </style>""",
        unsafe_allow_html=True,
    )

    r = get_redis()
    try:
        get_kotak()
    except Exception as e:
        st.error(f"❌ Kotak Neo login failed: {e}")
        st.info("Check KOTAK_* credentials in .env and restart.")
        st.stop()

    st.session_state["light_mode"] = True

    if "sync_started" not in st.session_state:
        sync_cnc(r)
        sync_mtf(r)
        sync_fo_positions(r)
        threading.Thread(target=background_sync, args=(r,), daemon=True).start()
        st.session_state["sync_started"] = True

    col_logo, col_nav, col_info = st.columns([1, 5, 2])
    with col_logo:
        st.markdown(":material/bar_chart: **Portfolio**")
    with col_nav:
        nav_options = [
            ":material/home: Portfolio",
            ":material/shopping_cart: Place Order",
            ":material/candlestick_chart: F&O Trading",
            ":material/notifications: GTT Orders",
            ":material/receipt_long: Order History",
        ]
        if "nav_page" in st.session_state:
            _redirect = st.session_state.pop("nav_page")
            if _redirect in nav_options:
                st.session_state["current_page"] = _redirect
                st.session_state["nav_radio"] = _redirect

        if "current_page" not in st.session_state:
            st.session_state["current_page"] = ":material/home: Portfolio"

        nav_index = (
            nav_options.index(st.session_state["current_page"])
            if st.session_state["current_page"] in nav_options
            else 0
        )

        page = st.radio(
            "nav",
            nav_options,
            index=nav_index,
            horizontal=True,
            label_visibility="collapsed",
            key="nav_radio",
        )
        st.session_state["current_page"] = page
    with col_info:
        from datetime import datetime as _dt
        last = r.get(REDIS_CNC_LAST_SYNC)
        ucc = os.getenv("KOTAK_UCC", "")
        from config import INDIA_TZ as _TZ
        _now = _dt.now(_TZ)
        _mopen = _now.replace(hour=9, minute=15, second=0, microsecond=0)
        _mclose = _now.replace(hour=15, minute=30, second=0, microsecond=0)
        _is_open = _mopen <= _now <= _mclose and _now.weekday() < 5
        _mkt_html = (
            '<span style="color:#1ba572;font-weight:600">● Live</span>'
            if _is_open else
            '<span style="color:#e34a3a;font-weight:600">● Closed</span>'
        )
        if last:
            try:
                _sync_dt = _dt.fromisoformat(last)
                _diff = int((_now - _sync_dt).total_seconds())
                _ago = f"{_diff // 60}m ago" if _diff >= 60 else f"{_diff}s ago"
            except Exception:
                _ago = last[:16]
            sync_str = f":material/sync: {_ago} · "
        else:
            sync_str = ""
        st.markdown(
            f"<div style='font-size:12px;color:#666;text-align:right;padding-top:6px'>"
            f"{_mkt_html} &nbsp;·&nbsp; {sync_str}:material/account_balance: {ucc}"
            f"</div>",
            unsafe_allow_html=True,
        )

    if not st.session_state.get("otp_pending", False):
        qs_col1, qs_col2, qs_col3 = st.columns([1.2, 4, 1])

        with qs_col1:
            qs_exch = st.selectbox(
                "exch",
                ["NSE", "BSE"],
                label_visibility="collapsed",
                key="qs_exch",
            )

        with qs_col2:
            if qs_exch == "BSE":
                qs_stock_data = load_stocks_bse()
                qs_format = lambda x: (
                    "🔍 Search any BSE stock..." if x == ""
                    else f"{x} — {qs_stock_data.get(x, {}).get('name', '')}"
                )
            else:
                qs_stock_data = load_stocks_nse()
                qs_format = lambda x: (
                    "🔍 Search any NSE stock..." if x == ""
                    else f"{x} — {qs_stock_data.get(x, {}).get('name', '')}"
                )

            qs_symbols = [""] + sorted(qs_stock_data.keys())
            qs_selected = st.selectbox(
                "search",
                options=qs_symbols,
                format_func=qs_format,
                label_visibility="collapsed",
                key="qs_stock",
            )

        with qs_col3:
            if st.button(
                "🚀 Go",
                use_container_width=True,
                key="qs_go",
                type="primary",
                disabled=(not qs_selected),
            ):
                if qs_selected:
                    st.session_state["prefill_symbol"]     = qs_selected
                    st.session_state["prefill_action"]     = "BUY"
                    st.session_state["prefill_exchange"]   = qs_exch
                    st.session_state["prefill_order_type"] = "CNC"
                    st.session_state["nav_page"]           = ":material/shopping_cart: Place Order"
                    st.rerun()

    st.markdown("<hr style='margin:4px 0 8px 0;border-color:#e5e7ee'>", unsafe_allow_html=True)

    if page == ":material/home: Portfolio":
        page_dashboard(r)
    elif page == ":material/shopping_cart: Place Order":
        page_place_order(r)
    elif page == ":material/candlestick_chart: F&O Trading":
        render_fo_page(r)
    elif page == ":material/notifications: GTT Orders":
        page_gtt(r)
    elif page == ":material/receipt_long: Order History":
        page_order_history(r)


if __name__ == "__main__":
    main()
