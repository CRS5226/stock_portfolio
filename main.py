import os
import threading
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw

from auth.kotak_client import get_redis, get_kotak, load_stocks_nse, load_stocks_bse
from data.sync import sync_cnc, sync_mtf, sync_fo_positions, background_sync
from ui.dashboard import page_dashboard
from ui.place_order_ui import page_place_order
from ui.order_history import page_order_history, page_gtt
from fo.fo_ui_helper import render_fo_page
from config import REDIS_CNC_LAST_SYNC


def _make_favicon():
    """Green rounded-square with a white stock-chart polyline."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Rounded green background
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=12, fill="#1ba572")
    # Chart polyline (scaled to 64px)
    pts = [(8, 48), (20, 32), (32, 40), (44, 20), (56, 28)]
    d.line(pts, fill="#ffffff", width=4)
    return img


def main():
    st.set_page_config(page_title="Portfolio Manager", page_icon=_make_favicon(), layout="wide")
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
        div[data-testid="stButton"] button[data-testid="baseButton-primary"]:has(p:contains("search")) {
            width: 38px !important;
            min-width: 38px !important;
            padding: 0 !important;
            border-radius: 8px !important;
        }
        div[data-testid="stVerticalBlock"] > div:first-child { padding-top: 0 !important; }
        .stRadio > div { gap: 0.3rem !important; }
        [data-testid="stRadio"] label p { font-size: 13.5px !important; }
        [data-testid="stHorizontalBlock"] { align-items: center !important; }
        div[data-testid="stHorizontalBlock"] { gap: 0.6rem; }
        hr { margin: 0.6rem 0 !important; }
        .holdings-row:hover { background:#f0f2f5 !important; }
        div[data-testid="stSelectbox"] > div { min-height: 36px !important; font-size: 13px !important; }
        div[data-testid="stSelectbox"] > label { display: none !important; }
        [data-testid="stPopover"] button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 2px 6px !important;
            min-height: 28px !important;
            color: #555 !important;
            font-size: 18px !important;
            letter-spacing: 1px !important;
        }
        [data-testid="stPopover"] button:hover {
            background: #f0f2f6 !important;
            border-radius: 4px !important;
        }
        [data-testid="stPopover"] button svg { display: none !important; }
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

    col_logo, col_nav, col_search, col_info = st.columns([0.9, 3.5, 2.8, 1.8])
    with col_logo:
        st.markdown(
            "<div style='padding-top:4px'>"
            "<span style='font-size:20px;font-weight:800;color:#1ba572;"
            "letter-spacing:-0.5px;line-height:1.2'>&#9679; Portfolio</span>"
            "</div>",
            unsafe_allow_html=True,
        )
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
                st.session_state["nav_radio"] = _redirect

        if "nav_radio" not in st.session_state:
            st.session_state["nav_radio"] = ":material/home: Portfolio"

        page = st.radio(
            "nav",
            nav_options,
            horizontal=True,
            label_visibility="collapsed",
            key="nav_radio",
        )
    with col_search:
        if not st.session_state.get("otp_pending", False):
            sc1, sc2, sc3 = st.columns([0.9, 3, 0.6])
            with sc1:
                qs_exch = st.selectbox(
                    "exch",
                    ["NSE", "BSE"],
                    label_visibility="collapsed",
                    key="qs_exch",
                )
            with sc2:
                if qs_exch == "BSE":
                    qs_stock_data = load_stocks_bse()
                else:
                    qs_stock_data = load_stocks_nse()
                qs_symbols = sorted(qs_stock_data.keys())
                qs_selected = st.selectbox(
                    "search",
                    options=qs_symbols,
                    format_func=lambda x: f"{x} — {qs_stock_data.get(x, {}).get('name', '')}",
                    placeholder=f"Search any {qs_exch} stock...",
                    label_visibility="collapsed",
                    index=None,
                    key="qs_stock",
                )
            with sc3:
                if st.button(
                    ":material/search:",
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
            sync_str = f"↻ {_ago}"
        else:
            sync_str = "↻ —"
        _info_c1, _info_c2 = st.columns([0.7, 1])
        with _info_c1:
            if st.button(":material/sync: Sync", key="hdr_sync", use_container_width=True, help="Sync portfolio now"):
                with st.spinner("Syncing…"):
                    sync_cnc(r)
                    sync_mtf(r)
                    sync_fo_positions(r)
                st.rerun()
        with _info_c2:
            st.markdown(
                f"<div style='font-size:11px;color:#666;text-align:right;padding-top:8px;line-height:1.5'>"
                f"{_mkt_html}<br>{sync_str} · {ucc}"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── JS: Sell button red in popover + Sync button blue ──────────────────
    components.html("""
    <script>
    (function(){
      var doc = window.parent.document;
      function applyStyles(){
        doc.querySelectorAll('button[data-testid="baseButton-secondary"]').forEach(function(btn){
          var p = btn.querySelector('p');
          if(!p) return;
          var t = p.textContent.trim();
          var s = btn.style;
          if(t === 'Sell'){
            s.setProperty('background-color','#e34a3a','important');
            s.setProperty('color','#fff','important');
            s.setProperty('border','none','important');
            s.setProperty('border-radius','8px','important');
            s.setProperty('font-weight','600','important');
          } else if(t.includes('Sync')){
            s.setProperty('background-color','#1e88e5','important');
            s.setProperty('color','#fff','important');
            s.setProperty('border','none','important');
            s.setProperty('border-radius','8px','important');
          }
        });
      }
      applyStyles();
      new MutationObserver(applyStyles).observe(doc.body,{childList:true,subtree:true});
    })();
    </script>
    """, height=1, scrolling=False)
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
