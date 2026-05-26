import json
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import (
    REDIS_CNC_HOLDINGS,
    REDIS_CNC_LAST_SYNC,
    REDIS_MTF_POSITIONS,
)
from auth.kotak_client import get_kotak
from data.sync import sync_cnc, sync_mtf
from data.sync import sync_fo_positions
from data.prices import get_live_price, get_live_price_kotak
from ui.theme import get_theme


def page_dashboard(r):
    t = get_theme()
    st_autorefresh(interval=180000, key="dashboard_refresh")

    col_sync, col_last = st.columns([1, 5])
    with col_sync:
        if st.button("🔄 Sync", use_container_width=True):
            with st.spinner("Syncing..."):
                sync_cnc(r)
                sync_mtf(r)
                sync_fo_positions(r)
            st.rerun()
    with col_last:
        last = r.get(REDIS_CNC_LAST_SYNC)
        if last:
            st.caption(f"Last synced: {last[:19].replace('T',' ')} IST")

    avl = net = cash = 0.0
    funds_err = None
    try:
        fresh = get_kotak()
        limits = fresh.limits(segment="ALL", exchange="ALL", product="ALL")
        ldata = limits if isinstance(limits, dict) else {}
        cash = float(ldata.get("RmsPayInAmt", 0) or 0)
        net = float(ldata.get("Net", 0) or 0)
        avl = cash if cash > 0 else net
    except Exception as e:
        funds_err = str(e)

    raw_cnc = r.hgetall(REDIS_CNC_HOLDINGS)
    holdings_list = []
    if raw_cnc:
        for v in raw_cnc.values():
            h = json.loads(v)
            if h.get("quantity", 0) > 0 and h.get("average_price", 0) > 0:
                holdings_list.append(h)

    total_invested = total_current = 0.0
    for h in holdings_list:
        lp = get_live_price(r, h["symbol"]) or h["last_price"]
        total_invested += h["average_price"] * h["quantity"]
        total_current += lp * h["quantity"]

    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
    pnl_color = t["green"] if total_pnl >= 0 else t["red"]
    pnl_sign = "+" if total_pnl >= 0 else ""
    arrow = "▲" if total_pnl >= 0 else "▼"

    raw_mtf = r.hgetall(REDIS_MTF_POSITIONS)
    mtf_pos = []
    if raw_mtf:
        mtf_pos = [
            json.loads(v)
            for v in raw_mtf.values()
            if json.loads(v).get("quantity", 0) > 0
        ]
    mtf_warning_html = (
        '<div style="color:#ff9800;font-size:10px;margin-top:3px">'
        "⚠️ MTF positions active — interest charged daily</div>"
        if mtf_pos
        else ""
    )

    cnc_val = sum(
        h["average_price"] * h["quantity"]
        for h in holdings_list
        if h.get("product_type", "CNC") == "CNC"
    )
    mtf_val = sum(
        h["average_price"] * h["quantity"]
        for h in holdings_list
        if h.get("product_type") == "MTF"
    )

    col_funds, col_summary = st.columns([2, 3])
    with col_funds:
        if funds_err:
            st.warning(f"Funds: {funds_err}")
        else:
            st.markdown(
                f"""
            <div style="background:{t['funds_bg']};border-radius:10px;padding:20px 24px;
                        border:1px solid {t['card_border']};min-height:230px">
                <div style="color:{t['funds_caption']};font-size:11px;letter-spacing:.6px;
                            text-transform:uppercase">💰 Available Balance</div>
                <div style="color:{t['text_primary']};font-size:30px;font-weight:700;
                            margin-top:4px">₹ {avl:,.2f}</div>
                <div style="color:{t['funds_caption']};font-size:11px;margin-top:4px">
                    Ready to invest</div>
                {mtf_warning_html}
            </div>""",
                unsafe_allow_html=True,
            )

    with col_summary:
        if holdings_list:
            total_day_chg = sum(
                (
                    get_live_price_kotak(
                        h.get("exchange_identifier") or h.get("instrument_token", 0),
                        "nse_cm",
                    )
                    or h["last_price"]
                )
                * h["quantity"]
                - h["last_price"] * h["quantity"]
                for h in holdings_list
            )
            day_color = t["green"] if total_day_chg >= 0 else t["red"]
            day_sign = "+" if total_day_chg >= 0 else ""
            day_pct = (
                total_day_chg
                / (sum(h["last_price"] * h["quantity"] for h in holdings_list) or 1)
            ) * 100

            st.markdown(
                f"""
            <div style="background:{t['card_bg']};border-radius:10px;padding:20px 24px;
                        outline:1px solid {t['card_border']}">
                <div style="color:{t['text_muted']};font-size:11px;text-transform:uppercase;
                            letter-spacing:.5px">Current Value</div>
                <div style="color:{t['text_primary']};font-size:30px;font-weight:700;
                            margin:4px 0 16px 0">₹ {total_current:,.2f}</div>
                <div style="display:flex;justify-content:space-between;padding:12px 0;
                            border-top:1px solid {t['card_border']}">
                    <div>
                        <div style="color:{t['text_muted']};font-size:10px;text-transform:uppercase">Invested</div>
                        <div style="color:{t['text_primary']};font-size:14px;font-weight:600;
                                    margin-top:3px">₹ {total_invested:,.2f}</div>
                    </div>
                    <div style="text-align:center">
                        <div style="color:{t['text_muted']};font-size:10px;text-transform:uppercase">1D Returns</div>
                        <div style="color:{day_color};font-size:14px;font-weight:600;
                                    margin-top:3px">{day_sign}₹ {total_day_chg:,.2f}</div>
                        <div style="color:{day_color};font-size:11px">{day_sign}{day_pct:.2f}%</div>
                    </div>
                    <div style="text-align:right">
                        <div style="color:{t['text_muted']};font-size:10px;text-transform:uppercase">Total Returns</div>
                        <div style="color:{pnl_color};font-size:14px;font-weight:600;
                                    margin-top:3px">{pnl_sign}₹ {total_pnl:,.2f}</div>
                        <div style="background:{pnl_color};color:#fff;font-size:10px;
                                    font-weight:600;padding:1px 7px;border-radius:10px;
                                    display:inline-block;margin-top:2px">
                            {arrow} {pnl_sign}{total_pnl_pct:.2f}%</div>
                    </div>
                </div>
                <div style="display:flex;justify-content:space-between;padding-top:12px;gap:8px">
                    <div style="flex:1;text-align:center;padding:6px 4px;
                                background:{t['header_bg']};border-radius:6px">
                        <div style="color:{t['text_muted']};font-size:9px;text-transform:uppercase">CNC</div>
                        <div style="color:{t['text_primary']};font-size:12px;font-weight:600;
                                    margin-top:2px">₹{cnc_val:,.0f}</div>
                    </div>
                    <div style="flex:1;text-align:center;padding:6px 4px;
                                background:{t['header_bg']};border-radius:6px">
                        <div style="color:{t['text_muted']};font-size:9px;text-transform:uppercase">MTF</div>
                        <div style="color:{t['text_primary']};font-size:12px;font-weight:600;
                                    margin-top:2px">₹{mtf_val:,.0f}</div>
                    </div>
                    <div style="flex:1;text-align:center;padding:6px 4px;
                                background:{t['header_bg']};border-radius:6px">
                        <div style="color:{t['text_muted']};font-size:9px;text-transform:uppercase">MIS</div>
                        <div style="color:{t['text_muted']};font-size:12px;margin-top:2px">₹0</div>
                    </div>
                    <div style="flex:1;text-align:center;padding:6px 4px;
                                background:{t['header_bg']};border-radius:6px">
                        <div style="color:{t['text_muted']};font-size:9px;text-transform:uppercase">Futures</div>
                        <div style="color:{t['text_muted']};font-size:12px;margin-top:2px">₹0</div>
                    </div>
                    <div style="flex:1;text-align:center;padding:6px 4px;
                                background:{t['header_bg']};border-radius:6px">
                        <div style="color:{t['text_muted']};font-size:9px;text-transform:uppercase">Options</div>
                        <div style="color:{t['text_muted']};font-size:12px;margin-top:2px">₹0</div>
                    </div>
                </div>
            </div>""",
                unsafe_allow_html=True,
            )
        else:
            st.info("No holdings found. Click Sync.")

    st.markdown(
        f"<div style='margin-top:22px;color:{t['text_primary']};font-size:18px;"
        f"font-weight:700'>🏦 Holdings ({len(holdings_list)})</div>"
        f"<div style='color:{t['text_muted']};font-size:10px;margin-bottom:10px'>"
        f"Today's CNC orders appear here tomorrow · MTF holdings are pledged (interest charged daily)</div>",
        unsafe_allow_html=True,
    )

    if holdings_list:
        hcols = st.columns([2.5, 1.8, 1.5, 1.8, 0.7])
        header_data = [
            ("COMPANY", "left"),
            ("MARKET PRICE (1D)", "right"),
            ("RETURNS", "right"),
            ("CURRENT (INVESTED)", "right"),
            ("ACTION", "center"),
        ]
        for col, (label, align) in zip(hcols, header_data):
            col.markdown(
                f"<div style='color:{t['text_muted']};font-size:10px;font-weight:500;"
                f"letter-spacing:.4px;padding:6px 0;text-align:{align}'>{label}</div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            f"<hr style='margin:0 0 4px 0;border-color:{t['card_border']}'>",
            unsafe_allow_html=True,
        )

        for h in sorted(holdings_list, key=lambda x: x["symbol"]):
            symbol = h["symbol"]
            qty = h["quantity"]
            avg_price = h["average_price"]
            lp = (
                get_live_price_kotak(
                    h.get("exchange_identifier") or h.get("instrument_token", 0),
                    "nse_cm",
                )
                or get_live_price(r, symbol)
                or h["last_price"]
            )
            prev_close = h.get("last_price", 0)
            day_chg = lp - prev_close if prev_close else 0
            day_pct = (day_chg / prev_close * 100) if prev_close else 0
            day_color = t["green"] if day_chg >= 0 else t["red"]
            day_sign = "+" if day_chg >= 0 else ""
            invested = avg_price * qty
            cur_val = lp * qty
            pnl = cur_val - invested
            ret_pct = (pnl / invested * 100) if invested else 0
            badge = h.get("product_type", "CNC")
            exch = h.get("exchange", "NSE")
            pc = t["green"] if pnl >= 0 else t["red"]
            ps = "+" if pnl >= 0 else ""
            bc = "#ff9800" if badge == "MTF" else "#1976d2"

            row_cols = st.columns([2.5, 1.8, 1.5, 1.8, 0.7])

            row_cols[0].markdown(
                f"<div style='padding:10px 0'>"
                f"<div style='font-weight:600;color:{t['text_primary']};font-size:14px'>{symbol}</div>"
                f"<div style='color:{t['text_muted']};font-size:11px;margin-top:2px'>"
                f"{qty} shares &nbsp;·&nbsp; Avg ₹{avg_price:,.2f}</div>"
                f"<div style='margin-top:4px;display:flex;gap:5px'>"
                f"<span style='background:{bc};color:#fff;font-size:9px;font-weight:600;"
                f"padding:1px 6px;border-radius:3px'>{badge}</span>"
                f"<span style='background:{t['exch_bg']};color:{t['exch_text']};font-size:9px;"
                f"padding:1px 6px;border-radius:3px'>{exch}</span>"
                f"</div></div>",
                unsafe_allow_html=True,
            )

            row_cols[1].markdown(
                f"<div style='padding:10px 0;text-align:right'>"
                f"<div style='color:{t['text_primary']};font-weight:600;font-size:14px'>"
                f"₹{lp:,.2f}</div>"
                f"<div style='color:{day_color};font-size:11px;margin-top:2px'>"
                f"{day_sign}{day_chg:,.2f} ({day_sign}{day_pct:.2f}%)</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            row_cols[2].markdown(
                f"<div style='padding:10px 0;text-align:right'>"
                f"<div style='color:{pc};font-weight:700;font-size:13px'>{ps}{ret_pct:.2f}%</div>"
                f"<div style='color:{pc};font-size:11px;margin-top:2px'>{ps}₹{pnl:,.2f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            row_cols[3].markdown(
                f"<div style='padding:10px 0;text-align:right'>"
                f"<div style='color:{t['text_primary']};font-weight:600;font-size:14px'>"
                f"₹{cur_val:,.2f}</div>"
                f"<div style='color:{t['text_muted']};font-size:11px;margin-top:2px'>"
                f"₹{invested:,.2f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            with row_cols[4]:
                st.markdown("<div style='padding-top:10px'>", unsafe_allow_html=True)
                bcol1, bcol2 = st.columns(2)
                with bcol1:
                    if st.button(
                        "B",
                        key=f"buy_{symbol}",
                        use_container_width=True,
                        help=f"BUY {symbol}",
                    ):
                        st.session_state["prefill_symbol"] = symbol
                        st.session_state["prefill_action"] = "BUY"
                        st.session_state["prefill_exchange"] = exch
                        st.session_state["prefill_order_type"] = badge
                        st.session_state["nav_page"] = "🛒 Place Order"
                        st.rerun()
                with bcol2:
                    if st.button(
                        "S",
                        key=f"sell_{symbol}",
                        use_container_width=True,
                        help=f"SELL {symbol}",
                    ):
                        st.session_state["prefill_symbol"] = symbol
                        st.session_state["prefill_action"] = "SELL"
                        st.session_state["prefill_exchange"] = exch
                        st.session_state["prefill_order_type"] = badge
                        st.session_state["nav_page"] = "🛒 Place Order"
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown(
                f"<hr style='margin:0;border-color:{t['card_border']}'>",
                unsafe_allow_html=True,
            )

    if mtf_pos:
        st.markdown(
            f"<div style='margin-top:22px;color:{t['text_primary']};font-size:18px;"
            f"font-weight:700;margin-bottom:8px'>💳 MTF Open Positions ({len(mtf_pos)})</div>",
            unsafe_allow_html=True,
        )
        rows_html = ""
        for p in sorted(mtf_pos, key=lambda x: x["symbol"]):
            symbol = p["symbol"]
            qty = p["quantity"]
            avg_price = p["average_price"]
            lp = get_live_price(r, symbol) or p["last_price"]
            inv = avg_price * qty if avg_price else 0
            cur = lp * qty
            pnl = cur - inv
            pc = t["green"] if pnl >= 0 else t["red"]
            ps = "+" if pnl >= 0 else ""
            rows_html += f"""
            <tr class="holdings-row" style="border-bottom:1px solid {t['card_border']}">
                <td style="padding:9px 12px">
                    <div style="font-weight:600;color:{t['text_primary']};font-size:13px">{symbol}
                        <span style="background:#ff9800;color:#fff;font-size:9px;font-weight:600;
                                     padding:1px 6px;border-radius:3px;margin-left:6px">MTF</span>
                    </div>
                </td>
                <td style="padding:9px 12px;text-align:right;color:{t['text_secondary']};font-size:13px">{qty}</td>
                <td style="padding:9px 12px;text-align:right;color:{t['text_secondary']};font-size:13px">₹{avg_price:,.2f}</td>
                <td style="padding:9px 12px;text-align:right;color:{t['text_primary']};font-weight:600;font-size:13px">₹{lp:,.2f}</td>
                <td style="padding:9px 12px;text-align:right">
                    <div style="color:{pc};font-weight:600;font-size:13px">{ps}₹{pnl:,.2f}</div>
                </td>
                <td style="padding:9px 12px;text-align:right">
                    <div style="color:{t['text_primary']};font-weight:600;font-size:13px">₹{cur:,.2f}</div>
                    <div style="color:{t['text_muted']};font-size:11px">₹{inv:,.2f} inv.</div>
                </td>
            </tr>"""
        st.markdown(
            f"""
        <div style="background:{t['card_bg']};border-radius:10px;overflow:hidden;
                    border:1px solid {t['card_border']};margin-bottom:14px">
            <table style="width:100%;border-collapse:collapse">
                <thead><tr style="background:{t['header_bg']}">
                    <th style="padding:9px 12px;text-align:left;color:{t['text_muted']};font-size:11px;font-weight:500">COMPANY</th>
                    <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">QTY</th>
                    <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">AVG PRICE</th>
                    <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">MARKET PRICE</th>
                    <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">P&L</th>
                    <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">CURRENT (INVESTED)</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>""",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"<div style='margin-top:22px;color:{t['text_primary']};font-size:18px;"
        f"font-weight:700;margin-bottom:8px'>📋 Today's Orders</div>",
        unsafe_allow_html=True,
    )
    try:
        from datetime import datetime
        from config import INDIA_TZ as _TZ
        fresh = get_kotak()
        resp = fresh.order_report()
        items = (
            resp
            if isinstance(resp, list)
            else resp.get("data", []) if isinstance(resp, dict) else []
        )
        if items:
            order_rows_html = ""
            for o in items:
                time_val = (
                    o.get("ordTm")
                    or o.get("exchTmstp")
                    or o.get("flDtTm")
                    or o.get("hsUpTm")
                    or ""
                )
                time_str = str(time_val)[:8]
                sym = o.get("trdSym", "").replace("-EQ", "")
                exch = o.get("exSeg", "").replace("_cm", "").upper()
                otype = o.get("prod", "")
                act = "BUY" if o.get("trnsTp") == "B" else "SELL"
                act_color = t["green"] if act == "BUY" else t["red"]
                o_qty = o.get("qty", "")
                price = f"₹ {float(o.get('avgPrc',0) or 0):,.2f}"
                ord_id = o.get("nOrdNo", "")
                status_val = o.get("ordSt", "").upper()
                if "COMPLET" in status_val or status_val == "TRADED":
                    status_html = f'<span style="background:#22a06b;color:#fff;font-size:10px;padding:2px 7px;border-radius:4px">✓ {status_val}</span>'
                elif "REJECT" in status_val or "CANCEL" in status_val:
                    status_html = f'<span style="background:#eb5b3c;color:#fff;font-size:10px;padding:2px 7px;border-radius:4px">✗ {status_val}</span>'
                else:
                    status_html = f'<span style="background:#f59e0b;color:#fff;font-size:10px;padding:2px 7px;border-radius:4px">⏳ {status_val}</span>'
                order_rows_html += f"""
                <tr class="holdings-row" style="border-bottom:1px solid {t['card_border']}">
                    <td style="padding:9px 12px;color:{t['text_secondary']};font-size:12px">{time_str}</td>
                    <td style="padding:9px 12px;color:{t['text_primary']};font-weight:600;font-size:13px">{sym}</td>
                    <td style="padding:9px 12px;text-align:center;color:{t['text_secondary']};font-size:12px">{exch}</td>
                    <td style="padding:9px 12px;text-align:center;color:{t['text_secondary']};font-size:12px">{otype}</td>
                    <td style="padding:9px 12px;text-align:center;color:{act_color};font-weight:600;font-size:12px">{act}</td>
                    <td style="padding:9px 12px;text-align:right;color:{t['text_secondary']};font-size:13px">{o_qty}</td>
                    <td style="padding:9px 12px;text-align:right;color:{t['text_primary']};font-weight:600;font-size:13px">{price}</td>
                    <td style="padding:9px 12px;text-align:center">{status_html}</td>
                    <td style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px">{ord_id}</td>
                </tr>"""
            st.markdown(
                f"""
            <div style="background:{t['card_bg']};border-radius:10px;overflow:hidden;
                        border:1px solid {t['card_border']};margin-bottom:14px">
                <table style="width:100%;border-collapse:collapse">
                    <thead><tr style="background:{t['header_bg']}">
                        <th style="padding:9px 12px;text-align:left;color:{t['text_muted']};font-size:11px;font-weight:500">TIME</th>
                        <th style="padding:9px 12px;text-align:left;color:{t['text_muted']};font-size:11px;font-weight:500">SYMBOL</th>
                        <th style="padding:9px 12px;text-align:center;color:{t['text_muted']};font-size:11px;font-weight:500">EXCHANGE</th>
                        <th style="padding:9px 12px;text-align:center;color:{t['text_muted']};font-size:11px;font-weight:500">TYPE</th>
                        <th style="padding:9px 12px;text-align:center;color:{t['text_muted']};font-size:11px;font-weight:500">ACTION</th>
                        <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">QTY</th>
                        <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">PRICE</th>
                        <th style="padding:9px 12px;text-align:center;color:{t['text_muted']};font-size:11px;font-weight:500">STATUS</th>
                        <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">ORDER ID</th>
                    </tr></thead>
                    <tbody>{order_rows_html}</tbody>
                </table>
            </div>""",
                unsafe_allow_html=True,
            )
        else:
            now_ist = datetime.now(_TZ)
            market_open = now_ist.replace(hour=9, minute=15, second=0)
            market_close = now_ist.replace(hour=15, minute=30, second=0)
            if now_ist < market_open:
                msg = f"Market opens at 9:15 AM IST · {(market_open - now_ist).seconds // 60} mins to go"
            elif now_ist > market_close:
                msg = "Market closed for today · Opens tomorrow at 9:15 AM IST"
            else:
                msg = "No orders placed yet today"
            st.caption(f"📭 {msg}")
    except Exception as e:
        st.warning(f"Could not fetch today's orders: {e}")
