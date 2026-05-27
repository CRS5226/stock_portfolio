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

    # Dynamically group holdings by product_type
    from collections import defaultdict as _dd
    _alloc = _dd(float)
    for h in holdings_list:
        _alloc[h.get("product_type", "CNC")] += h["average_price"] * h["quantity"]
    cnc_val = _alloc.get("CNC", 0.0)
    mtf_val = _alloc.get("MTF", 0.0)
    etf_val = _alloc.get("ETF", 0.0)

    # ── 3-column summary metric cards ──────────────────────────────────────
    mc1, mc2, mc3 = st.columns(3)
    _card = (
        "background:{bg};border-radius:10px;padding:16px 20px;"
        "border-top:3px solid {accent};border:1px solid {border};"
        "box-shadow:0 1px 4px rgba(0,0,0,.06);height:118px;"
        "display:flex;flex-direction:column;justify-content:space-between;overflow:hidden"
    )
    with mc1:
        if funds_err:
            st.warning(f"Balance unavailable: {funds_err}")
        else:
            st.markdown(
                f"""<div style="{_card.format(bg=t['funds_bg'], accent='#1ba572', border=t['card_border'])}">
                    <div style="color:{t['text_muted']};font-size:10px;text-transform:uppercase;
                                letter-spacing:.5px;margin-bottom:6px">
                        Available Balance</div>
                    <div style="color:{t['text_primary']};font-size:26px;font-weight:700;
                                letter-spacing:-.5px">₹ {avl:,.2f}</div>
                    <div style="color:{t['text_muted']};font-size:11px;margin-top:4px">
                        Ready to invest{' · MTF active' if mtf_pos else ''}</div>
                </div>""",
                unsafe_allow_html=True,
            )
    with mc2:
        st.markdown(
            f"""<div style="{_card.format(bg=t['card_bg'], accent='#1976d2', border=t['card_border'])}">
                <div style="color:{t['text_muted']};font-size:10px;text-transform:uppercase;
                            letter-spacing:.5px;margin-bottom:6px">
                    Current Value</div>
                <div style="color:{t['text_primary']};font-size:26px;font-weight:700;
                            letter-spacing:-.5px">₹ {total_current:,.2f}</div>
                <div style="color:{t['text_muted']};font-size:11px;margin-top:4px">
                    Invested ₹ {total_invested:,.2f}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with mc3:
        st.markdown(
            f"""<div style="{_card.format(bg=t['card_bg'], accent=pnl_color, border=t['card_border'])}">
                <div style="color:{t['text_muted']};font-size:10px;text-transform:uppercase;
                            letter-spacing:.5px;margin-bottom:6px">
                    Total Returns</div>
                <div style="color:{pnl_color};font-size:26px;font-weight:700;
                            letter-spacing:-.5px">{pnl_sign}₹ {total_pnl:,.2f}</div>
                <div style="margin-top:6px">
                    <span style="background:{pnl_color};color:#fff;font-size:11px;font-weight:600;
                                 padding:2px 10px;border-radius:20px">
                        {arrow} {pnl_sign}{total_pnl_pct:.2f}%</span>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

    # ── Shared colour map (used by allocation bar + right panel) ────────────
    _TYPE_COLORS = {
        "CNC": "#1976d2", "MTF": "#ff9800", "ETF": "#8b5cf6",
        "MIS": "#e34a3a", "FO":  "#06b6d4", "CO":  "#ec4899",
        "BO":  "#10b981",
    }
    _DEFAULT_COLOR = "#6b7280"

    # ── Precompute enriched holdings (used by list AND right panel) ──────────
    _holdings_data = []
    for h in sorted(holdings_list, key=lambda x: x["symbol"]):
        _sym  = h["symbol"]
        _qty  = h["quantity"]
        _avg  = h["average_price"]
        _lp   = (
            get_live_price_kotak(
                h.get("exchange_identifier") or h.get("instrument_token", 0), "nse_cm"
            )
            or get_live_price(r, _sym)
            or h["last_price"]
        )
        _prev = h.get("last_price", 0)
        _dchg = _lp - _prev if _prev else 0
        _dpct = (_dchg / _prev * 100) if _prev else 0
        _inv  = _avg * _qty
        _cur  = _lp * _qty
        _pnl  = _cur - _inv
        _rpct = (_pnl / _inv * 100) if _inv else 0
        _holdings_data.append({
            "symbol": _sym, "qty": _qty, "avg_price": _avg,
            "lp": _lp, "prev_close": _prev,
            "day_chg": _dchg, "day_pct": _dpct,
            "invested": _inv, "cur_val": _cur,
            "pnl": _pnl, "ret_pct": _rpct,
            "badge": h.get("product_type", "CNC"),
            "exch": h.get("exchange", "NSE"),
        })

    _sorted_pnl = sorted(_holdings_data, key=lambda x: x["ret_pct"], reverse=True)
    _gainers    = [x for x in _sorted_pnl if x["pnl"] > 0][:3]
    _losers     = [x for x in reversed(_sorted_pnl) if x["pnl"] < 0][:3]

    # ── Two-column layout: Holdings list (left) + Insights panel (right) ────
    main_left, main_right = st.columns([3.2, 1.5])

    # ────────────────────────── LEFT: Holdings list ──────────────────────────
    with main_left:
        st.markdown(
            f"<div style='margin-top:18px;display:flex;align-items:center;gap:10px;margin-bottom:4px'>"
            f"<span style='color:{t['text_primary']};font-size:17px;font-weight:700'>Holdings</span>"
            f"<span style='background:#1976d2;color:#fff;font-size:11px;font-weight:600;"
            f"padding:2px 9px;border-radius:20px'>{len(holdings_list)}</span>"
            f"</div>"
            f"<div style='color:{t['text_muted']};font-size:10px;margin-bottom:10px'>"
            f"Today's CNC orders appear here tomorrow · MTF holdings are pledged (interest charged daily)</div>",
            unsafe_allow_html=True,
        )

        if _holdings_data:
            hcols = st.columns([2.5, 1.8, 1.5, 1.8, 0.7])
            for col, (label, align) in zip(hcols, [
                ("", "left"), ("MARKET PRICE", "right"),
                ("RETURNS", "right"), ("CURRENT (INVESTED)", "right"), ("", "center"),
            ]):
                col.markdown(
                    f"<div style='color:{t['text_muted']};font-size:10px;font-weight:500;"
                    f"letter-spacing:.4px;padding:4px 0;text-align:{align}'>{label}</div>",
                    unsafe_allow_html=True,
                )

            for hd in _holdings_data:
                symbol    = hd["symbol"]
                qty       = hd["qty"]
                avg_price = hd["avg_price"]
                lp        = hd["lp"]
                day_chg   = hd["day_chg"]
                day_pct   = hd["day_pct"]
                day_color = t["green"] if day_chg >= 0 else t["red"]
                day_sign  = "+" if day_chg >= 0 else ""
                invested  = hd["invested"]
                cur_val   = hd["cur_val"]
                pnl       = hd["pnl"]
                ret_pct   = hd["ret_pct"]
                badge     = hd["badge"]
                exch      = hd["exch"]
                pc        = t["green"] if pnl >= 0 else t["red"]
                ps        = "+" if pnl >= 0 else ""
                bc        = "#ff9800" if badge == "MTF" else ("#8b5cf6" if badge == "ETF" else "#1976d2")
                row_border = t["green"] if pnl >= 0 else t["red"]

                row_cols = st.columns([2.5, 1.8, 1.5, 1.8, 0.7])

                row_cols[0].markdown(
                    f"<div style='padding:10px 0 10px 10px;border-left:3px solid {row_border};'>"
                    f"<div style='font-weight:700;color:{t['text_primary']};font-size:14px'>{symbol}</div>"
                    f"<div style='margin-top:5px;display:flex;gap:5px;align-items:center'>"
                    f"<span style='background:{bc};color:#fff;font-size:9px;font-weight:600;"
                    f"padding:2px 7px;border-radius:20px'>{badge}</span>"
                    f"<span style='background:{t['exch_bg']};color:{t['exch_text']};font-size:9px;"
                    f"font-weight:500;padding:2px 7px;border-radius:20px'>{exch}</span>"
                    f"<span style='background:#f0f2f6;color:{t['text_muted']};font-size:9px;"
                    f"padding:2px 7px;border-radius:20px'>{qty} shares</span>"
                    f"</div>"
                    f"<div style='color:{t['text_muted']};font-size:11px;margin-top:4px'>"
                    f"Avg ₹{avg_price:,.2f}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                row_cols[1].markdown(
                    f"<div style='padding:10px 0;text-align:right'>"
                    f"<div style='color:{t['text_primary']};font-weight:600;font-size:14px'>"
                    f"₹{lp:,.2f}</div>"
                    f"<div style='color:{day_color};font-size:11px;margin-top:3px'>"
                    f"{day_sign}{day_chg:,.2f} ({day_sign}{day_pct:.2f}%)</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                row_cols[2].markdown(
                    f"<div style='padding:10px 0;text-align:right'>"
                    f"<div style='color:{pc};font-weight:700;font-size:13px'>{ps}{ret_pct:.2f}%</div>"
                    f"<div style='color:{pc};font-size:11px;margin-top:3px'>{ps}₹{pnl:,.2f}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                row_cols[3].markdown(
                    f"<div style='padding:10px 0;text-align:right'>"
                    f"<div style='color:{t['text_primary']};font-weight:600;font-size:14px'>"
                    f"₹{cur_val:,.2f}</div>"
                    f"<div style='color:{t['text_muted']};font-size:11px;margin-top:3px'>"
                    f"₹{invested:,.2f} inv.</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                with row_cols[4]:
                    with st.popover("⋮", use_container_width=True):
                        if st.button("Buy", key=f"buy_{symbol}", use_container_width=True, type="primary"):
                            st.session_state["prefill_symbol"] = symbol
                            st.session_state["prefill_action"] = "BUY"
                            st.session_state["prefill_exchange"] = exch
                            st.session_state["prefill_order_type"] = badge
                            st.session_state["nav_page"] = ":material/shopping_cart: Place Order"
                            st.rerun()
                        if st.button("Sell", key=f"sell_{symbol}", use_container_width=True):
                            st.session_state["prefill_symbol"] = symbol
                            st.session_state["prefill_action"] = "SELL"
                            st.session_state["prefill_exchange"] = exch
                            st.session_state["prefill_order_type"] = badge
                            st.session_state["nav_page"] = ":material/shopping_cart: Place Order"
                            st.rerun()

                st.markdown(
                    f"<hr style='margin:0;border-color:{t['card_border']}'>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                f"""<div style="text-align:center;padding:40px 20px;background:{t['card_bg']};
                               border-radius:12px;border:1px dashed {t['card_border']};margin-top:8px">
                    <div style="font-size:36px;margin-bottom:10px">🏦</div>
                    <div style="color:{t['text_primary']};font-size:15px;font-weight:600;margin-bottom:4px">
                        No holdings found</div>
                    <div style="color:{t['text_muted']};font-size:12px">
                        Click <b>Sync</b> above to load your portfolio from Kotak Neo</div>
                </div>""",
                unsafe_allow_html=True,
            )

    # ────────────────────────── RIGHT: Insights panel ───────────────────────
    with main_right:
        _card_s = (
            f"background:{t['card_bg']};border-radius:10px;"
            f"padding:14px 14px;border:1px solid {t['card_border']};"
            f"box-shadow:0 1px 4px rgba(0,0,0,.06);margin-top:18px;margin-bottom:14px"
        )
        _sec_lbl = (
            f"font-size:10px;font-weight:600;text-transform:uppercase;"
            f"letter-spacing:.6px;color:{t['text_muted']};margin-bottom:8px"
        )

        # ── Donut chart (CSS conic-gradient, no external lib needed) ────────
        if _holdings_data and total_invested > 0:
            # Types with actual value → used for gradient segments
            _donut_types = [
                (pt, val) for pt, val in sorted(
                    _alloc.items(), key=lambda x: (x[0] != "CNC", -x[1])
                ) if val > 0
            ]
            _stops, _cum = [], 0.0
            for _pt, _val in _donut_types:
                _pct = _val / total_invested * 100
                _c   = _TYPE_COLORS.get(_pt, _DEFAULT_COLOR)
                _stops.append(f"{_c} {_cum:.2f}% {_cum + _pct:.2f}%")
                _cum += _pct
            _gradient = ", ".join(_stops)
            _cval = (
                f"₹{total_invested / 100000:.1f}L"
                if total_invested >= 100000
                else f"₹{total_invested:,.0f}"
            )
            # Legend helper — builds one type row
            _tmuted = t["text_muted"]
            _tsec   = t["text_secondary"]
            def _leg_row(_pt):
                _v  = _alloc.get(_pt, 0)
                _op = "1" if _v > 0 else "0.35"
                _tc = _tsec if _v > 0 else _tmuted
                return (
                    f"<div style='display:flex;align-items:center;gap:5px;margin-bottom:8px'>"
                    f"<span style='width:9px;height:9px;border-radius:2px;flex-shrink:0;"
                    f"background:{_TYPE_COLORS[_pt]};display:inline-block;opacity:{_op}'></span>"
                    f"<div style='line-height:1.25'>"
                    f"<div style='font-size:11px;font-weight:600;color:{_tc}'>{_pt}</div>"
                    f"<div style='font-size:10px;color:{_tmuted};white-space:nowrap'>"
                    f"₹{_v:,.0f} · {_v/total_invested*100:.1f}%</div>"
                    f"</div>"
                    f"</div>"
                )

            _col_left  = "".join(_leg_row(p) for p in ["CNC", "MTF", "ETF"])
            _col_right = "".join(_leg_row(p) for p in ["MIS", "FO"])

            st.markdown(
                f"<div style='{_card_s}'>"
                f"<div style='{_sec_lbl}'>Allocation</div>"
                f"<div style='display:flex;align-items:center;gap:12px'>"
                # ── donut ──
                f"  <div style='position:relative;width:100px;height:100px;flex-shrink:0'>"
                f"    <div style='width:100px;height:100px;border-radius:50%;"
                f"background:conic-gradient({_gradient})'></div>"
                f"    <div style='position:absolute;top:50%;left:50%;"
                f"transform:translate(-50%,-50%);"
                f"width:62px;height:62px;background:{t['card_bg']};border-radius:50%;"
                f"display:flex;flex-direction:column;align-items:center;"
                f"justify-content:center;gap:1px'>"
                f"      <span style='font-size:11px;font-weight:700;"
                f"color:{t['text_primary']}'>{_cval}</span>"
                f"      <span style='font-size:8px;color:{t['text_muted']};"
                f"letter-spacing:.3px'>INVESTED</span>"
                f"    </div>"
                f"  </div>"
                # ── left legend: CNC / MTF / ETF ──
                f"  <div style='flex:1;min-width:0'>{_col_left}</div>"
                # ── right legend: MIS / FO ──
                f"  <div style='flex:1;min-width:0'>{_col_right}</div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ── Top Gainers ──────────────────────────────────────────────────────
        if _gainers:
            _g_items = ""
            for _i, g in enumerate(_gainers):
                _sep = f"border-bottom:1px solid {t['card_border']};" if _i < len(_gainers) - 1 else ""
                _g_items += (
                    f"<div style='display:flex;justify-content:space-between;"
                    f"align-items:center;padding:7px 0;{_sep}'>"
                    f"<div>"
                    f"<div style='font-size:12px;font-weight:700;"
                    f"color:{t['text_primary']}'>{g['symbol']}</div>"
                    f"<div style='font-size:10px;color:{t['text_muted']};margin-top:1px'>"
                    f"{g['qty']} shares</div>"
                    f"</div>"
                    f"<div style='text-align:right'>"
                    f"<div style='font-size:12px;font-weight:700;color:{t['green']}'>"
                    f"+{g['ret_pct']:.2f}%</div>"
                    f"<div style='font-size:10px;color:{t['green']};margin-top:1px'>"
                    f"+₹{g['pnl']:,.0f}</div>"
                    f"</div>"
                    f"</div>"
                )
            st.markdown(
                f"<div style='{_card_s}'>"
                f"<div style='{_sec_lbl}'>▲ Top Gainers</div>"
                f"{_g_items}"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ── Top Losers ───────────────────────────────────────────────────────
        if _losers:
            _l_items = ""
            for _i, l in enumerate(_losers):
                _sep = f"border-bottom:1px solid {t['card_border']};" if _i < len(_losers) - 1 else ""
                _l_items += (
                    f"<div style='display:flex;justify-content:space-between;"
                    f"align-items:center;padding:7px 0;{_sep}'>"
                    f"<div>"
                    f"<div style='font-size:12px;font-weight:700;"
                    f"color:{t['text_primary']}'>{l['symbol']}</div>"
                    f"<div style='font-size:10px;color:{t['text_muted']};margin-top:1px'>"
                    f"{l['qty']} shares</div>"
                    f"</div>"
                    f"<div style='text-align:right'>"
                    f"<div style='font-size:12px;font-weight:700;color:{t['red']}'>"
                    f"{l['ret_pct']:.2f}%</div>"
                    f"<div style='font-size:10px;color:{t['red']};margin-top:1px'>"
                    f"-₹{abs(l['pnl']):,.0f}</div>"
                    f"</div>"
                    f"</div>"
                )
            st.markdown(
                f"<div style='{_card_s}'>"
                f"<div style='{_sec_lbl}'>▼ Top Losers</div>"
                f"{_l_items}"
                f"</div>",
                unsafe_allow_html=True,
            )

    if mtf_pos:
        st.markdown(
            f"<div style='margin-top:22px;display:flex;align-items:center;gap:10px;margin-bottom:4px'>"
            f"<span style='color:{t['text_primary']};font-size:17px;font-weight:700'>MTF Open Positions</span>"
            f"<span style='background:#ff9800;color:#fff;font-size:11px;font-weight:600;"
            f"padding:2px 9px;border-radius:20px'>{len(mtf_pos)}</span>"
            f"</div>"
            f"<div style='color:{t['text_muted']};font-size:10px;margin-bottom:10px'>"
            f"Margin Trading Facility positions · Interest charged daily</div>",
            unsafe_allow_html=True,
        )

        mtf_hcols = st.columns([2.5, 1.8, 1.5, 1.8])
        for col, (label, align) in zip(mtf_hcols, [
            ("", "left"), ("MARKET PRICE", "right"),
            ("RETURNS", "right"), ("CURRENT (INVESTED)", "right"),
        ]):
            col.markdown(
                f"<div style='color:{t['text_muted']};font-size:10px;font-weight:500;"
                f"letter-spacing:.4px;padding:4px 0;text-align:{align}'>{label}</div>",
                unsafe_allow_html=True,
            )

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
            day_chg = lp - (p.get("last_price", lp) or lp)
            day_pct = (day_chg / p.get("last_price", lp) * 100) if p.get("last_price", 0) else 0
            day_color = t["green"] if day_chg >= 0 else t["red"]
            day_sign = "+" if day_chg >= 0 else ""
            ret_pct = (pnl / inv * 100) if inv else 0
            row_border = t["green"] if pnl >= 0 else t["red"]
            exch = p.get("exchange", "NSE")

            mtf_row_cols = st.columns([2.5, 1.8, 1.5, 1.8])

            mtf_row_cols[0].markdown(
                f"<div style='padding:10px 0 10px 10px;border-left:3px solid {row_border};'>"
                f"<div style='font-weight:700;color:{t['text_primary']};font-size:14px'>{symbol}</div>"
                f"<div style='margin-top:5px;display:flex;gap:5px;align-items:center'>"
                f"<span style='background:#ff9800;color:#fff;font-size:9px;font-weight:600;"
                f"padding:2px 7px;border-radius:20px'>MTF</span>"
                f"<span style='background:{t['exch_bg']};color:{t['exch_text']};font-size:9px;"
                f"font-weight:500;padding:2px 7px;border-radius:20px'>{exch}</span>"
                f"<span style='background:#f0f2f6;color:{t['text_muted']};font-size:9px;"
                f"padding:2px 7px;border-radius:20px'>{qty} shares</span>"
                f"</div>"
                f"<div style='color:{t['text_muted']};font-size:11px;margin-top:4px'>"
                f"Avg ₹{avg_price:,.2f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            mtf_row_cols[1].markdown(
                f"<div style='padding:10px 0;text-align:right'>"
                f"<div style='color:{t['text_primary']};font-weight:600;font-size:14px'>"
                f"₹{lp:,.2f}</div>"
                f"<div style='color:{day_color};font-size:11px;margin-top:3px'>"
                f"{day_sign}{day_chg:,.2f} ({day_sign}{day_pct:.2f}%)</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            mtf_row_cols[2].markdown(
                f"<div style='padding:10px 0;text-align:right'>"
                f"<div style='color:{pc};font-weight:700;font-size:13px'>{ps}{ret_pct:.2f}%</div>"
                f"<div style='color:{pc};font-size:11px;margin-top:3px'>{ps}₹{pnl:,.2f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            mtf_row_cols[3].markdown(
                f"<div style='padding:10px 0;text-align:right'>"
                f"<div style='color:{t['text_primary']};font-weight:600;font-size:14px'>"
                f"₹{cur:,.2f}</div>"
                f"<div style='color:{t['text_muted']};font-size:11px;margin-top:3px'>"
                f"₹{inv:,.2f} inv.</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            st.markdown(
                f"<hr style='margin:0;border-color:{t['card_border']}'>",
                unsafe_allow_html=True,
            )

    st.markdown(
        f"<div style='margin-top:22px;color:{t['text_primary']};font-size:18px;"
        f"font-weight:700;margin-bottom:8px'>Today's Orders</div>",
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
                time_str = ""
                if time_val:
                    ts = str(time_val).strip()
                    for _fmt in (
                        "%Y/%m/%d %H:%M:%S", "%d-%b-%Y %H:%M:%S",
                        "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S",
                        "%Y/%m/%d %H:%M",    "%d-%b-%Y %H:%M",
                    ):
                        try:
                            _dt = datetime.strptime(ts[:19], _fmt)
                            time_str = _dt.strftime("%d %b %H:%M")
                            break
                        except Exception:
                            continue
                    if not time_str:
                        time_str = ts[:16]
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
