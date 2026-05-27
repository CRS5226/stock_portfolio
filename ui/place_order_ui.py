import json
import time
import streamlit as st

from config import (
    INDIA_TZ,
    INDEX_CODES,
    REDIS_CNC_HOLDINGS,
    REDIS_MTF_POSITIONS,
    REDIS_OTP_PENDING,
)
from auth.kotak_client import (
    get_kotak,
    load_stocks_nse,
    load_stocks_bse,
    load_stocks_mtf_mis,
)
from data.prices import get_price_with_fallback, get_margin_required, get_margin_required_mis
from data.sync import sync_cnc, sync_mtf
from orders.otp import generate_otp, store_otp, verify_otp
from orders.place_order import place_order, save_order_history
from utils.telegram import send_telegram_otp
from ui.theme import get_theme


def page_place_order(r):
    t = get_theme()
    otp_pending = st.session_state.get("otp_pending", False)

    if "prefill_symbol" in st.session_state:
        st.session_state["_pf_symbol"]     = st.session_state.pop("prefill_symbol")
        st.session_state["_pf_action"]     = st.session_state.pop("prefill_action",     "BUY")
        st.session_state["_pf_exchange"]   = st.session_state.pop("prefill_exchange",   "NSE")
        st.session_state["_pf_order_type"] = st.session_state.pop("prefill_order_type", "CNC")

    prefill_symbol     = st.session_state.get("_pf_symbol",     None)
    prefill_action     = st.session_state.get("_pf_action",     "BUY")
    prefill_exchange   = st.session_state.get("_pf_exchange",   "NSE")
    prefill_order_type = st.session_state.get("_pf_order_type", "CNC")

    st.markdown(
        f"""
    <div style="margin-bottom:16px">
        <div style="color:{t['text_muted']};font-size:11px;text-transform:uppercase;
                    letter-spacing:.5px;margin-bottom:8px">Order Type</div>
    </div>""",
        unsafe_allow_html=True,
    )

    _ot_default = {
        "CNC": "CNC — Delivery",
        "MTF": "MTF — Margin",
        "MIS": "MIS — Intraday",
    }.get(prefill_order_type, "CNC — Delivery")
    _ot_options = [
        "CNC — Delivery",
        "MTF — Margin",
        "MIS — Intraday",
    ]
    _ot_index = _ot_options.index(_ot_default) if _ot_default in _ot_options else 0

    order_type = st.radio(
        "Order Type",
        _ot_options,
        index=_ot_index,
        horizontal=True,
        label_visibility="collapsed",
        disabled=otp_pending,
        key="po_order_type",
    )
    is_cnc = order_type.startswith("CNC")
    is_mtf = order_type.startswith("MTF")
    is_mis = order_type.startswith("MIS")
    prod = (
        "MTF" if is_mtf
        else "MIS" if is_mis
        else "CNC"
    )

    if is_mtf:
        st.markdown(
            """
        <div style="background:#fff8e6;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                    border-left:3px solid #ff9800;font-size:12px;color:#7a5a00">
            💳 <b>MTF (Margin)</b> — Buy with leverage up to 5x. Interest charged daily. NSE only.
        </div>""",
            unsafe_allow_html=True,
        )
    elif is_mis:
        st.markdown(
            """
        <div style="background:#fff3f3;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                    border-left:3px solid #e34a3a;font-size:12px;color:#7a1a1a">
            ⚡ <b>MIS (Intraday)</b> — Auto square-off at 3:20 PM IST. NSE only.
        </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
        <div style="background:#f0faf5;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                    border-left:3px solid #1ba572;font-size:12px;color:#0a4a2a">
            📦 <b>CNC (Delivery)</b> — Full payment. Shares delivered T+1. NSE and BSE available.
        </div>""",
            unsafe_allow_html=True,
        )

    exchange = "NSE"
    if is_cnc and not otp_pending:
        _exch_idx = 1 if prefill_exchange == "BSE" else 0
        exchange = st.radio(
            "Exchange",
            ["NSE", "BSE"],
            index=_exch_idx,
            horizontal=True,
            disabled=otp_pending,
            key="po_exchange",
        )

    if is_cnc:
        stock_data = (
            load_stocks_bse() if exchange == "BSE" else load_stocks_nse()
        )
        symbols = sorted(stock_data.keys())
        format_fn = lambda x: f"{x} — {stock_data.get(x,{}).get('name','')}"
    else:
        mtf_mis_stocks = {**load_stocks_mtf_mis()}
        symbols = sorted(
            s for s in mtf_mis_stocks.keys() if not (is_mis and s in INDEX_CODES)
        )
        stock_data = None
        format_fn = lambda x: f"{x} — {mtf_mis_stocks.get(x,'')}"

    if not symbols:
        st.warning("No stocks found.")
        return

    default_idx = 0
    if prefill_symbol and prefill_symbol in symbols:
        default_idx = symbols.index(prefill_symbol)

    selected = st.selectbox(
        "🔍 Search stock",
        options=symbols,
        index=default_idx,
        format_func=format_fn,
        disabled=otp_pending,
    )

    if is_cnc and stock_data:
        trd_sym = stock_data.get(selected, {}).get("trading_symbol")
        instr_token = stock_data.get(selected, {}).get("instrument_token", 0)
        exch_seg = "bse_cm" if (is_cnc and exchange == "BSE") else "nse_cm"
        lot_size = stock_data.get(selected, {}).get("lot_size", 1)
    else:
        trd_sym = f"{selected}-EQ"
        exch_seg = "nse_cm"
        instr_token = 0
        lot_size = 1
        raw_h = r.hget(REDIS_CNC_HOLDINGS, selected)
        if raw_h:
            instr_token = json.loads(raw_h).get("instrument_token", 0)
        raw_p = r.hget(REDIS_MTF_POSITIONS, selected)
        if raw_p:
            instr_token = json.loads(raw_p).get("instrument_token", 0)
        if not instr_token:
            nse_stocks = load_stocks_nse()
            instr_token = nse_stocks.get(selected, {}).get("instrument_token", 0)

    if exchange == "BSE" and lot_size > 1:
        st.warning(
            f"⚠️ BSE Board Lot Size: **{lot_size}** — qty must be multiple of {lot_size}"
        )

    live_price, price_source = get_price_with_fallback(
        r, selected, instr_token, exch_seg
    )
    live_price = live_price or 0.0
    source_tag = (
        "📡 Live"
        if price_source == "kotak"
        else ("📊 Redis" if price_source == "redis" else "⚠️ No price")
    )

    st.markdown(
        f"""
    <div style="background:{t['card_bg']};border-radius:12px;padding:16px 24px;
                outline:1px solid {t['card_border']};margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <div style="color:{t['text_primary']};font-size:24px;font-weight:700">
                    ₹ {live_price:,.2f}</div>
                <div style="color:{t['text_muted']};font-size:11px;margin-top:2px">
                    {selected} · {exchange} · {source_tag}</div>
            </div>
        </div>
    </div>""",
        unsafe_allow_html=True,
    )

    order_kind = st.radio(
        "Order Kind",
        ["MKT", "L", "SL"],
        horizontal=True,
        label_visibility="visible",
        disabled=otp_pending,
        help="MKT=Market  ·  L=Limit  ·  SL=Stop-Loss Limit",
        key="po_order_kind",
    )

    limit_price = 0.0
    trigger_price = 0.0

    _action_idx = 1 if prefill_action == "SELL" else 0
    _safe_px = max(float(round(live_price, 2)), 0.01)

    if order_kind == "L":
        limit_price = st.number_input(
            "Limit Price (₹)",
            min_value=0.01,
            value=_safe_px,
            step=0.05,
            format="%.2f",
            disabled=otp_pending,
            key="po_limit_price",
        )
    elif order_kind == "SL":
        _sl_trigger_default = (
            max(round(_safe_px * 1.01, 2), 0.01)
            if st.session_state.get("po_action", "BUY") == "BUY"
            else max(round(_safe_px * 0.99, 2), 0.01)
        )
        _sl_limit_default = (
            max(round(_safe_px * 1.015, 2), 0.01)
            if st.session_state.get("po_action", "BUY") == "BUY"
            else max(round(_safe_px * 0.985, 2), 0.01)
        )
        col_tp, col_lp = st.columns(2)
        with col_tp:
            trigger_price = st.number_input(
                "Trigger Price (₹)",
                min_value=0.01,
                value=_sl_trigger_default,
                step=0.05,
                format="%.2f",
                disabled=otp_pending,
                key="po_trigger_price",
                help="BUY: set above current price · SELL: set below current price · Min 0.5% distance from LTP",
            )
        with col_lp:
            limit_price = st.number_input(
                "Limit Price (₹)",
                min_value=0.01,
                value=_sl_limit_default,
                step=0.05,
                format="%.2f",
                disabled=otp_pending,
                key="po_limit_price",
                help="BUY: set slightly above trigger · SELL: set slightly below trigger",
            )
    col1, col2 = st.columns([3, 2])
    with col1:
        qty_step = lot_size if (exchange == "BSE" and lot_size > 1) else 1
        qty_val = lot_size if (exchange == "BSE" and lot_size > 1) else 1
        qty = st.number_input(
            "Quantity", min_value=1, step=qty_step, value=qty_val,
            disabled=otp_pending, key="po_qty",
        )
    with col2:
        action = st.radio(
            "Action",
            ["BUY", "SELL"],
            index=_action_idx,
            horizontal=True,
            disabled=otp_pending,
            key="po_action",
        )

    if exchange == "BSE" and lot_size > 1 and qty % lot_size != 0:
        st.error(f"❌ Qty must be multiple of {lot_size}")
        return

    display_price = limit_price if order_kind in ("L", "SL") else live_price
    total_val = qty * display_price

    margin = mis_margin = None
    if is_mtf and live_price and not otp_pending and instr_token:
        with st.spinner("Fetching margin..."):
            margin = get_margin_required(instr_token, "nse_cm", qty)
    if is_mis and live_price and not otp_pending and instr_token:
        with st.spinner("Fetching intraday margin..."):
            mis_margin = get_margin_required_mis(instr_token, "nse_cm", qty)

    avl = 0.0
    try:
        fresh = get_kotak()
        limits = fresh.limits(segment="ALL", exchange="ALL", product="ALL")
        ldata = limits if isinstance(limits, dict) else {}
        cash = float(ldata.get("RmsPayInAmt", 0) or 0)
        net = float(ldata.get("Net", 0) or 0)
        avl = cash if cash > 0 else net
    except:
        pass

    req = (
        margin
        if (is_mtf and margin and margin > 0)
        else (mis_margin if (is_mis and mis_margin and mis_margin > 0) else total_val)
    )
    sufficient = avl >= req if req > 0 else True
    bal_color = t["green"] if sufficient else t["red"]

    margin_line = ""
    if is_mtf and margin and margin > 0:
        broker_funds = total_val - margin
        your_pct = (margin / total_val * 100) if total_val else 0
        margin_line = f"Your margin: ₹{margin:,.2f} ({your_pct:.0f}%)  ·  Broker: ₹{broker_funds:,.2f}"
    elif is_mis and mis_margin and mis_margin > 0:
        mis_pct = (mis_margin / total_val * 100) if total_val else 0
        margin_line = f"Intraday margin: ₹{mis_margin:,.2f} ({mis_pct:.0f}%)"
    elif is_cnc:
        margin_line = "Full payment required"

    st.markdown(
        f"""
    <div style="background:{t['card_bg']};border-radius:12px;padding:16px 24px;
                outline:1px solid {t['card_border']};margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;margin-bottom:10px">
            <div style="color:{t['text_muted']};font-size:12px">Order Value</div>
            <div style="color:{t['text_primary']};font-size:12px;font-weight:600">₹ {total_val:,.2f}</div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:10px">
            <div style="color:{t['text_muted']};font-size:12px">Required</div>
            <div style="color:{t['text_primary']};font-size:12px;font-weight:600">₹ {req:,.2f}</div>
        </div>
        <div style="display:flex;justify-content:space-between;
                    padding-top:10px;border-top:1px solid {t['card_border']}">
            <div style="color:{t['text_muted']};font-size:12px">Balance</div>
            <div style="color:{bal_color};font-size:12px;font-weight:700">
                ₹ {avl:,.2f} {'✓' if sufficient else '✗ Insufficient'}</div>
        </div>
        {f'<div style="color:{t["text_muted"]};font-size:11px;margin-top:8px">{margin_line}</div>' if margin_line else ''}
    </div>""",
        unsafe_allow_html=True,
    )

    if not otp_pending:
        order_kind_label = {
            "MKT": "Market",
            "L": "Limit",
            "SL": "SL-Limit",
        }.get(order_kind, order_kind)
        _ico = ":material/arrow_upward:" if action == "BUY" else ":material/arrow_downward:"
        btn_label = f"{_ico} {action} · {prod} · {exchange} · {order_kind_label} · ₹{total_val:,.2f}"
        _btn_col = "#1ba572" if action == "BUY" else "#e34a3a"
        st.html(f"""<style>
div[data-testid="stButton"] button[data-testid="baseButton-primary"] {{
    background-color: {_btn_col} !important;
    background:       {_btn_col} !important;
    background-image: none        !important;
    border-color:     {_btn_col} !important;
}}
</style>""")
        if st.button(btn_label, use_container_width=True, type="primary"):
            action_color = "#1ba572" if action == "BUY" else "#e34a3a"
            action_emoji = "🟢" if action == "BUY" else "🔴"
            loading_placeholder = st.empty()
            loading_placeholder.markdown(f"""
            <div style="background:#f8f9fa;border-radius:12px;padding:20px 24px;
                        outline:2px solid {action_color};margin-bottom:16px;text-align:center">
                <div style="display:flex;align-items:center;justify-content:center;gap:12px">
                    <div style="width:20px;height:20px;border:3px solid {action_color};
                                border-top-color:transparent;border-radius:50%;
                                animation:spin 0.8s linear infinite"></div>
                    <div style="color:{action_color};font-size:15px;font-weight:600">
                        {action_emoji} Sending OTP to Telegram...
                    </div>
                </div>
                <div style="color:#7a7a8c;font-size:11px;margin-top:8px">
                    Do not click again — OTP is being generated
                </div>
            </div>
            <style>
            @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
            </style>
            """, unsafe_allow_html=True)

            try:
                print(f"[BUY CLICK] kind={order_kind} prod={prod} exch={exchange} "
                      f"sym={selected} act={action} qty={qty} "
                      f"lp={live_price} lim={limit_price} trg={trigger_price}")
                otp = generate_otp()
                store_otp(
                    r, otp, selected, action, qty, live_price, prod, exchange,
                    order_kind, limit_price, trigger_price,
                    0, 0, 0, 0,
                )
                sent = send_telegram_otp(
                    otp, selected, action, qty, live_price, prod, exchange,
                    order_kind, limit_price, trigger_price,
                    0, 0, 0, 0,
                )
                if sent:
                    loading_placeholder.empty()
                    st.session_state["otp_pending"] = True
                    st.session_state["otp_order"] = {
                        "symbol": selected, "action": action, "qty": qty,
                        "price": live_price, "order_type": prod,
                        "exchange": exchange, "trading_symbol": trd_sym,
                        "order_kind": order_kind, "limit_price": limit_price,
                        "trigger_price": trigger_price,
                    }
                    st.rerun()
                else:
                    loading_placeholder.empty()
                    tg_err = st.session_state.get("_last_tg_err") or "Unknown"
                    st.error(f"❌ Failed to send OTP via Telegram — {tg_err}")
            except Exception as e:
                loading_placeholder.empty()
                st.error(f"❌ Unexpected error while sending OTP: {e}")
                st.exception(e)

    if otp_pending:
        order = st.session_state.get("otp_order", {})
        ok_lbl = {
            "MKT": "Market",
            "L": f"Limit @ ₹{order.get('limit_price',0):,.2f}",
            "SL": f"SL-Limit  Trigger:₹{order.get('trigger_price',0):,.2f}  Limit:₹{order.get('limit_price',0):,.2f}",
        }.get(order.get("order_kind", "MKT"), "")
        st.markdown(
            f"""
        <div style="background:{t['card_bg']};border-radius:12px;padding:16px 24px;
                    outline:1px solid {t['card_border']};margin-bottom:16px">
            <div style="color:{t['text_primary']};font-size:14px;font-weight:600;margin-bottom:4px">
                🔐 Confirm Order</div>
            <div style="color:{t['text_muted']};font-size:12px">
                {order.get('order_type','CNC')} [{order.get('exchange','NSE')}]
                &nbsp;·&nbsp; {ok_lbl}
                &nbsp;·&nbsp; {order.get('action')} {order.get('qty')} × {order.get('symbol')}
                &nbsp;@&nbsp; ₹{order.get('price',0):,.2f}
            </div>
        </div>""",
            unsafe_allow_html=True,
        )

        ttl = r.ttl(REDIS_OTP_PENDING)
        if ttl > 0:
            st.info(f"⏳ OTP sent to Telegram — valid for **{ttl}** seconds")
            entered = st.text_input(
                "Enter 6-digit OTP",
                max_chars=6,
                key="otp_input",
                placeholder="e.g. 482910",
            )
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                if st.button(
                    "✅ Confirm & Place Order", use_container_width=True, type="primary"
                ):
                    if not entered:
                        st.error("Enter the OTP first.")
                    else:
                        data, status = verify_otp(r, entered)
                        if status == "ok":
                            with st.spinner("Placing order..."):
                                order_id, err = place_order(
                                    data["symbol"],
                                    data["action"],
                                    data["qty"],
                                    data["order_type"],
                                    data.get("exchange", "NSE"),
                                    data.get("trading_symbol"),
                                    data.get("order_kind", "MKT"),
                                    data.get("limit_price", 0),
                                    data.get("trigger_price", 0),
                                )
                            if order_id:
                                save_order_history(
                                    r,
                                    data["symbol"],
                                    data["action"],
                                    data["qty"],
                                    data["price"],
                                    order_id,
                                    data["order_type"],
                                    data.get("exchange", "NSE"),
                                    data.get("order_kind", "MKT"),
                                    data.get("limit_price", 0),
                                    data.get("trigger_price", 0),
                                )
                                if data["order_type"] == "CNC":
                                    sync_cnc(r)
                                elif data["order_type"] == "MTF":
                                    sync_mtf(r)
                                st.success(f"✅ Order placed! ID: `{order_id}`")
                                for k in [
                                    "otp_pending", "otp_order",
                                    "_pf_symbol", "_pf_action", "_pf_exchange", "_pf_order_type",
                                    "po_order_type", "po_order_kind", "po_exchange", "po_action",
                                    "po_trigger_price", "po_limit_price", "po_qty",
                                ]:
                                    st.session_state.pop(k, None)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ Order failed: {err}")
                                for k in ["otp_pending", "otp_order"]:
                                    st.session_state.pop(k, None)
                        elif status == "expired":
                            st.error("⏰ OTP expired.")
                            st.session_state.pop("otp_pending", None)
                        elif status == "invalid":
                            st.error("❌ Wrong OTP.")
            with col_cancel:
                if st.button("❌ Cancel", use_container_width=True):
                    r.delete(REDIS_OTP_PENDING)
                    for k in [
                        "otp_pending", "otp_order",
                        "_pf_symbol", "_pf_action", "_pf_exchange", "_pf_order_type",
                        "po_order_type", "po_order_kind", "po_exchange", "po_action",
                        "po_trigger_price", "po_limit_price", "po_qty",
                    ]:
                        st.session_state.pop(k, None)
                    st.rerun()
        else:
            st.error("⏰ OTP expired.")
            st.session_state.pop("otp_pending", None)
            if st.button("🔁 Resend OTP", use_container_width=True):
                otp = generate_otp()
                store_otp(
                    r, otp,
                    order.get("symbol"), order.get("action"), order.get("qty"),
                    order.get("price"), order.get("order_type", "CNC"),
                    order.get("exchange", "NSE"), order.get("order_kind", "MKT"),
                    order.get("limit_price", 0), order.get("trigger_price", 0),
                    0, 0, 0, 0,
                )
                send_telegram_otp(
                    otp,
                    order.get("symbol"), order.get("action"), order.get("qty"),
                    order.get("price"), order.get("order_type", "CNC"),
                    order.get("exchange", "NSE"), order.get("order_kind", "MKT"),
                    order.get("limit_price", 0), order.get("trigger_price", 0),
                    0, 0, 0, 0,
                )
                st.session_state["otp_pending"] = True
                st.rerun()
