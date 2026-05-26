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

