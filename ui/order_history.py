import io
import json
import time
import streamlit as st

from config import REDIS_CNC_HOLDINGS
from auth.kotak_client import get_kotak, load_stocks_nse
from data.prices import get_price_with_fallback
from data.sync import sync_cnc, sync_mtf, sync_fo_positions
from orders.place_order import get_order_history, get_fo_orders
from ui.theme import get_theme


def _to_csv(rows: list) -> bytes:
    if not rows:
        return b""
    import csv
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def _empty_state(msg="No orders yet."):
    st.markdown(
        f"""<div style="text-align:center;padding:32px 20px;background:#fafbfc;
                       border-radius:10px;border:1px dashed #e0e3ea;margin-top:8px">
            <div style="font-size:30px;margin-bottom:8px">📋</div>
            <div style="color:#555;font-size:14px;font-weight:600">{msg}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def page_order_history(r):
    st.header(":material/receipt_long: Order History — Kotak Neo")
    all_orders = get_order_history(r)
    fo_orders = get_fo_orders(r)

    # ── Global symbol filter ────────────────────────────────────────────────
    fc1, fc2 = st.columns([3, 1])
    with fc1:
        sym_filter = st.text_input(
            ":material/search: Filter by symbol",
            placeholder="e.g. RELIANCE",
            label_visibility="collapsed",
            key="oh_sym_filter",
        ).strip().upper()
    with fc2:
        all_rows_csv = [
            {
                "Time": o.get("time", "")[:19].replace("T", " "),
                "Symbol": o.get("symbol", ""),
                "Exchange": o.get("exchange", "NSE"),
                "Type": o.get("order_type", ""),
                "Order": o.get("order_kind", "MKT"),
                "Action": o.get("action", ""),
                "Qty": o.get("qty", ""),
                "Price": o.get("price", 0),
                "Order ID": o.get("order_id", ""),
            }
            for o in all_orders
        ]
        st.download_button(
            label=":material/download: Export CSV",
            data=_to_csv(all_rows_csv),
            file_name="order_history.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if sym_filter:
        all_orders = [o for o in all_orders if sym_filter in o.get("symbol", "").upper()]
        fo_orders  = [o for o in fo_orders  if sym_filter in o.get("trading_symbol", "").upper()]

    tab1, tab2, tab3, tab4 = st.tabs([
        ":material/inventory_2: CNC",
        ":material/credit_card: MTF",
        ":material/bolt: Intraday",
        ":material/candlestick_chart: F&O",
    ])

    def render_table(orders):
        if orders:
            rows = [
                {
                    "Time": o.get("time", "")[:19].replace("T", " "),
                    "Symbol": o.get("symbol", ""),
                    "Exchange": o.get("exchange", "NSE"),
                    "Order": o.get("order_kind", "MKT"),
                    "Action": o.get("action", ""),
                    "Qty": o.get("qty", ""),
                    "Price": f"₹ {o.get('price', 0):,.2f}",
                    "Order ID": o.get("order_id", ""),
                }
                for o in orders
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            _empty_state()

    with tab1:
        render_table([o for o in all_orders if o.get("order_type", "CNC") == "CNC"])
    with tab2:
        render_table([o for o in all_orders if o.get("order_type", "") == "MTF"])
    with tab3:
        render_table([o for o in all_orders if o.get("order_type", "") == "MIS"])
    with tab4:
        if fo_orders:
            st.dataframe(
                [
                    {
                        "Time": o.get("time", "")[:19].replace("T", " "),
                        "Symbol": o.get("trading_symbol", ""),
                        "Type": o.get("contract_type", ""),
                        "Action": o.get("action", ""),
                        "Lots": o.get("lots", ""),
                        "Qty": o.get("quantity", ""),
                        "Order ID": o.get("order_id", ""),
                    }
                    for o in fo_orders
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No F&O orders yet.")


def page_gtt(r):
    t = get_theme()

    st.markdown(
        """
    <div style="background:#f0faf5;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                border-left:3px solid #1ba572;font-size:12px;color:#0a4a2a">
        🔔 <b>GTT (Good Till Triggered)</b> — Stays active until triggered. Kotak monitors price 24/7. No OTP needed.
    </div>""",
        unsafe_allow_html=True,
    )

    tab_place, tab_active = st.tabs(["📝 Place GTT", "📋 Active GTTs"])

    with tab_place:
        nse_stocks = load_stocks_nse()
        if not nse_stocks:
            st.warning("config_kotak_nse.json not found.")
            return

        symbols = sorted(nse_stocks.keys())
        selected = st.selectbox(
            "🔍 Search stock (NSE only)",
            options=symbols,
            format_func=lambda x: f"{x} — {nse_stocks.get(x,{}).get('name','')}",
            key="gtt_symbol",
        )
        trd_sym = nse_stocks.get(selected, {}).get("trading_symbol", f"{selected}-EQ")
        instr_token = nse_stocks.get(selected, {}).get("instrument_token", 0)

        live_px, src = get_price_with_fallback(r, selected, instr_token, "nse_cm")
        live_px = live_px or 0.0
        src_tag = (
            "📡 Live"
            if src == "kotak"
            else ("📊 Redis" if src == "redis" else "⚠️ No price")
        )

        st.markdown(
            f"""
        <div style="background:{t['card_bg']};border-radius:12px;padding:16px 24px;
                    outline:1px solid {t['card_border']};margin-bottom:16px">
            <div style="color:{t['text_primary']};font-size:24px;font-weight:700">₹ {live_px:,.2f}</div>
            <div style="color:{t['text_muted']};font-size:11px;margin-top:2px">
                {selected} · NSE · {src_tag}</div>
        </div>""",
            unsafe_allow_html=True,
        )

        gc1, gc2 = st.columns([3, 2])
        with gc1:
            gtt_qty = st.number_input(
                "Quantity", min_value=1, step=1, value=1, key="gtt_qty"
            )
        with gc2:
            gtt_action = st.radio(
                "Transaction", ["BUY", "SELL"], horizontal=True, key="gtt_action"
            )

        pc1, pc2 = st.columns(2)
        with pc1:
            gtt_trigger = st.number_input(
                "Trigger Price (₹)",
                min_value=0.01,
                value=float(round(live_px or 100, 2)),
                step=0.05,
                format="%.2f",
                key="gtt_trigger",
                help="Price at which GTT fires",
            )
        with pc2:
            gtt_limit = st.number_input(
                "Limit Price (₹)",
                min_value=0.01,
                value=float(round((live_px or 100) * 0.999, 2)),
                step=0.05,
                format="%.2f",
                key="gtt_limit",
                help="Price at which order executes after trigger",
            )

        gtt_total = gtt_qty * gtt_limit
        st.markdown(
            f"""
        <div style="background:{t['card_bg']};border-radius:12px;padding:16px 24px;
                    outline:1px solid {t['card_border']};margin-bottom:16px">
            <div style="display:flex;justify-content:space-between;margin-bottom:10px">
                <div style="color:{t['text_muted']};font-size:12px">Trigger</div>
                <div style="color:{t['text_primary']};font-size:12px;font-weight:600">₹ {gtt_trigger:,.2f}</div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:10px">
                <div style="color:{t['text_muted']};font-size:12px">Limit</div>
                <div style="color:{t['text_primary']};font-size:12px;font-weight:600">₹ {gtt_limit:,.2f}</div>
            </div>
            <div style="display:flex;justify-content:space-between;padding-top:10px;
                        border-top:1px solid {t['card_border']}">
                <div style="color:{t['text_muted']};font-size:12px">Order Value</div>
                <div style="color:{t['text_primary']};font-size:12px;font-weight:700">₹ {gtt_total:,.2f}</div>
            </div>
        </div>""",
            unsafe_allow_html=True,
        )

        btn_label = (
            f"{'🟢 BUY' if gtt_action == 'BUY' else '🔴 SELL'} · GTT · "
            f"Trigger ₹{gtt_trigger:,.2f} · Limit ₹{gtt_limit:,.2f}"
        )
        if st.button(btn_label, use_container_width=True, type="primary"):
            try:
                with st.spinner("Placing GTT order..."):
                    client = get_kotak()
                    resp = client.place_gtt_order(
                        trading_symbol=trd_sym,
                        exchange_segment="nse_cm",
                        transaction_type="B" if gtt_action == "BUY" else "S",
                        product="CNC",
                        quantity=str(gtt_qty),
                        price=str(gtt_limit),
                        trigger_price=str(gtt_trigger),
                    )
                print(f"[GTT RAW] {resp}")
                gtt_id = None
                if isinstance(resp, dict):
                    gtt_id = (
                        resp.get("id")
                        or resp.get("gttId")
                        or resp.get("data", {}).get("id")
                        if isinstance(resp.get("data"), dict)
                        else None
                    )
                if gtt_id:
                    st.success(f"✅ GTT placed! ID: `{gtt_id}`")
                else:
                    st.success(f"✅ GTT placed! Response: `{resp}`")
            except Exception as e:
                st.error(f"❌ GTT failed: {e}")

    with tab_active:
        if st.button("🔄 Refresh", key="gtt_refresh"):
            st.rerun()

        try:
            client = get_kotak()
            gtts_resp = client.get_gtts()
        except Exception as e:
            st.error(f"❌ Could not fetch GTTs: {e}")
            return

        items = []
        if isinstance(gtts_resp, list):
            items = gtts_resp
        elif isinstance(gtts_resp, dict):
            raw = gtts_resp.get("data", []) or gtts_resp.get("gtts", [])
            if isinstance(raw, list):
                items = raw

        st.markdown(
            f"<div style='color:{t['text_primary']};font-size:18px;font-weight:700;margin:10px 0 8px 0'>"
            f"📋 Active GTTs ({len(items)})</div>",
            unsafe_allow_html=True,
        )

        if not items:
            st.caption("📭 No active GTTs.")
            return

        rows_html = ""
        gtt_id_options = []
        for g in items:
            gid = (
                g.get("id") or g.get("gttId") or g.get("gtt_id") or g.get("orderId") or ""
            )
            sym = g.get("trading_symbol") or g.get("tradingSymbol") or g.get("trdSym") or ""
            tt = g.get("transaction_type") or g.get("transactionType") or g.get("trnsTp") or ""
            tt_disp = "BUY" if tt in ("B", "BUY") else ("SELL" if tt in ("S", "SELL") else tt)
            tt_color = t["green"] if tt_disp == "BUY" else t["red"]
            q = g.get("quantity") or g.get("qty") or 0
            tp = g.get("trigger_price") or g.get("triggerPrice") or g.get("trgPrc") or 0
            pr = g.get("price") or g.get("prc") or 0
            stt = g.get("status") or g.get("ordSt") or ""
            try:
                tp = float(tp)
                pr = float(pr)
            except:
                pass
            rows_html += f"""
            <tr class="holdings-row" style="border-bottom:1px solid {t['card_border']}">
                <td style="padding:9px 12px;color:{t['text_muted']};font-size:11px">{gid}</td>
                <td style="padding:9px 12px;color:{t['text_primary']};font-weight:600;font-size:13px">{sym}</td>
                <td style="padding:9px 12px;text-align:center;color:{tt_color};font-weight:600;font-size:12px">{tt_disp}</td>
                <td style="padding:9px 12px;text-align:right;color:{t['text_secondary']};font-size:13px">{q}</td>
                <td style="padding:9px 12px;text-align:right;color:{t['text_primary']};font-size:13px">₹{tp:,.2f}</td>
                <td style="padding:9px 12px;text-align:right;color:{t['text_primary']};font-size:13px">₹{pr:,.2f}</td>
                <td style="padding:9px 12px;text-align:center;color:{t['text_secondary']};font-size:11px">{stt}</td>
            </tr>"""
            if gid:
                gtt_id_options.append(str(gid))

        st.markdown(
            f"""
        <div style="background:{t['card_bg']};border-radius:10px;overflow:hidden;
                    outline:1px solid {t['card_border']};margin-bottom:14px">
            <table style="width:100%;border-collapse:collapse">
                <thead>
                    <tr style="background:{t['header_bg']}">
                        <th style="padding:10px 12px;text-align:left;color:{t['text_muted']};font-size:11px;font-weight:500">ID</th>
                        <th style="padding:10px 12px;text-align:left;color:{t['text_muted']};font-size:11px;font-weight:500">SYMBOL</th>
                        <th style="padding:10px 12px;text-align:center;color:{t['text_muted']};font-size:11px;font-weight:500">TYPE</th>
                        <th style="padding:10px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">QTY</th>
                        <th style="padding:10px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">TRIGGER</th>
                        <th style="padding:10px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">LIMIT</th>
                        <th style="padding:10px 12px;text-align:center;color:{t['text_muted']};font-size:11px;font-weight:500">STATUS</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>""",
            unsafe_allow_html=True,
        )

        if gtt_id_options:
            dc1, dc2 = st.columns([3, 1])
            with dc1:
                selected_gtt = st.selectbox(
                    "Select GTT to delete", options=gtt_id_options, key="gtt_del_sel"
                )
            with dc2:
                st.markdown("<div style='padding-top:24px'>", unsafe_allow_html=True)
                if st.button("🗑️ Delete Selected GTT", use_container_width=True):
                    try:
                        client = get_kotak()
                        del_resp = client.delete_gtt_order(id=selected_gtt)
                        st.success(f"✅ GTT `{selected_gtt}` deleted. Response: `{del_resp}`")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Delete failed: {e}")
                st.markdown("</div>", unsafe_allow_html=True)
