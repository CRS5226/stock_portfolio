import json
import time
import streamlit as st
from datetime import datetime

from config import (
    INDIA_TZ,
    INDEX_MAP,
    CURRENCY_SYMBOLS,
    COMMODITY_SYMBOLS,
    REDIS_FO_POSITIONS,
    REDIS_FO_LAST_SYNC,
    REDIS_FO_OTP,
    CONFIG_FO_FILE,
    CONFIG_FO_BSE_FILE,
)
from auth.kotak_client import _create_kotak_client
from data.prices import get_live_price_fo
from data.sync import sync_fo_positions
from orders.otp import generate_otp, store_fo_otp, verify_fo_otp
from orders.place_order import place_fo_order, save_fo_order, get_fo_orders
from utils.telegram import send_fo_otp
from ui.theme import get_theme


@st.cache_data(ttl=300)
def load_fo_stocks():
    import os
    if not os.path.exists(CONFIG_FO_FILE):
        return {}
    with open(CONFIG_FO_FILE) as f:
        data = json.load(f)
    return {
        s["stock_code"]: s.get("name", s["stock_code"])
        for s in data.get("stocks", [])
        if s.get("stock_code")
    }


@st.cache_data(ttl=300)
def load_fo_bse_stocks():
    import os
    if not os.path.exists(CONFIG_FO_BSE_FILE):
        return {}
    with open(CONFIG_FO_BSE_FILE) as f:
        data = json.load(f)
    return {
        s["stock_code"]: s.get("name", s["stock_code"])
        for s in data.get("stocks", [])
        if s.get("stock_code")
    }


def _parse_expiry_to_dt(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%d%b%Y")
    except:
        pass
    try:
        return datetime.fromtimestamp(int(s))
    except:
        pass
    return datetime.max


def _format_expiry(s: str) -> str:
    try:
        datetime.strptime(s, "%d%b%Y")
        return s
    except:
        pass
    try:
        return datetime.fromtimestamp(int(s)).strftime("%d%b%Y")
    except:
        return s


def get_expiries(contracts: list) -> list:
    raw = set(c.get("pExpiryDate", "") for c in contracts if c.get("pExpiryDate"))
    return sorted(raw, key=_parse_expiry_to_dt)


@st.cache_data(ttl=300)
def fetch_contracts(stock_code: str) -> list:
    fo_symbol = INDEX_MAP.get(stock_code, stock_code)
    try:
        client = _create_kotak_client()
        contracts = client.search_scrip(
            exchange_segment="nse_fo",
            symbol=fo_symbol,
            expiry="",
            option_type="",
            strike_price="",
        )
        if not isinstance(contracts, list):
            return []
        exact = [c for c in contracts if c.get("pSymbolName") == fo_symbol]
        print(f"[NSE FO] {fo_symbol}: {len(exact)} contracts")
        return exact
    except Exception as e:
        print(f"[NSE FO ERROR] {e}")
        return []


@st.cache_data(ttl=300)
def fetch_contracts_bse(stock_code: str) -> list:
    try:
        client = _create_kotak_client()
        contracts = client.search_scrip(
            exchange_segment="bse_fo",
            symbol=stock_code,
            expiry="",
            option_type="",
            strike_price="",
        )
        if not isinstance(contracts, list):
            return []
        exact = [c for c in contracts if c.get("pSymbolName") == stock_code]
        print(f"[BSE FO] {stock_code}: {len(exact)} contracts")
        return exact
    except Exception as e:
        print(f"[BSE FO ERROR] {e}")
        return []


@st.cache_data(ttl=300)
def fetch_contracts_currency(symbol: str) -> list:
    try:
        client = _create_kotak_client()
        contracts = client.search_scrip(
            exchange_segment="cde_fo",
            symbol=symbol,
            expiry="",
            option_type="",
            strike_price="",
        )
        if not isinstance(contracts, list):
            return []
        exact = [c for c in contracts if c.get("pSymbolName") == symbol]
        print(f"[CURRENCY] {symbol}: {len(exact)} contracts")
        return exact
    except Exception as e:
        print(f"[CURRENCY ERROR] {e}")
        return []


@st.cache_data(ttl=300)
def fetch_contracts_commodity(symbol: str) -> list:
    try:
        client = _create_kotak_client()
        contracts = client.search_scrip(
            exchange_segment="mcx_fo",
            symbol=symbol,
            expiry="",
            option_type="",
            strike_price="",
        )
        if not isinstance(contracts, list):
            return []
        futures = [
            c
            for c in contracts
            if str(c.get("pInstType", "")).strip() in ("FUTCOM", "FUTCOMDTY")
            and c.get("pSymbolName") == symbol
            and c.get("pExpiryDate")
        ]
        print(f"[MCX] {symbol}: {len(futures)} futures")
        return futures
    except Exception as e:
        print(f"[MCX ERROR] {e}")
        return []


def fetch_contract_prices(contracts: list, exchange_segment: str = "nse_fo") -> dict:
    if not contracts:
        return {}
    try:
        client = _create_kotak_client()
        token_to_trd = {}
        tokens = []
        for c in contracts:
            sym = str(c.get("pSymbol", ""))
            if sym:
                token_to_trd[sym] = c["pTrdSymbol"]
                tokens.append(
                    {"instrument_token": sym, "exchange_segment": exchange_segment}
                )

        if not tokens:
            return {}

        price_map = {}
        for i in range(0, len(tokens), 50):
            batch = tokens[i : i + 50]
            try:
                resp = client.quotes(instrument_tokens=batch, quote_type="ltp")
                if isinstance(resp, list):
                    for item in resp:
                        token = str(item.get("exchange_token", ""))
                        ltp_raw = item.get("ltp", "0") or "0"
                        trd_sym = token_to_trd.get(token)
                        if trd_sym:
                            price_map[trd_sym] = float(ltp_raw)
            except Exception as e:
                print(f"[PRICE BATCH ERROR] {e}")

        print(f"[PRICES {exchange_segment}] fetched {len(price_map)}")
        return price_map
    except Exception as e:
        print(f"[PRICE ERROR] {e}")
        return {}


def get_futures_nse(contracts: list) -> list:
    return [c for c in contracts if c.get("pInstType") in ("FUTSTK", "FUTIDX")]


def get_options_nse(contracts: list) -> list:
    return [c for c in contracts if c.get("pInstType") in ("OPTSTK", "OPTIDX")]


def get_futures_bse(contracts: list) -> list:
    return [c for c in contracts if c.get("pInstType") in ("SF", "IF")]


def get_options_bse(contracts: list) -> list:
    return [c for c in contracts if c.get("pInstType") in ("SO", "IO")]


def get_futures_currency(contracts: list) -> list:
    return [c for c in contracts if c.get("pInstType") == "FUTCUR"]


def get_options_currency(contracts: list) -> list:
    return [c for c in contracts if c.get("pInstType") == "OPTCUR"]


def get_strikes(contracts: list, expiry: str, opt_type: str) -> list:
    filtered = [
        c
        for c in contracts
        if c.get("pExpiryDate") == expiry and c.get("pOptionType") == opt_type
    ]
    seen_strikes = set()
    raw_strikes = set()
    for c in filtered:
        strike_raw = c.get("dStrikePrice;", 0) or 0
        strike_val = int(float(strike_raw) / 100)
        if strike_val in seen_strikes:
            continue
        raw_strikes.add(strike_val)
        seen_strikes.add(strike_val)
    return sorted(raw_strikes)


def get_contract(
    contracts: list, expiry: str, opt_type: str, strike: int
) -> dict | None:
    matches = [
        c for c in contracts
        if c.get("pExpiryDate") == expiry
        and c.get("pOptionType") == opt_type
        and int(float(c.get("dStrikePrice;", 0) or 0) / 100) == strike
    ]
    if not matches:
        return None
    for c in matches:
        trd = c.get("pTrdSymbol", "")
        sym = c.get("pSymbolName", "")
        if trd.startswith(sym) and sym not in ("FINNIFTY", "MIDCPNIFTY", "BANKNIFTY", "NIFTYNXT50"):
            return c
    for c in matches:
        trd = c.get("pTrdSymbol", "")
        if not any(trd.startswith(idx) for idx in ("FINNIFTY", "MIDCPNIFTY", "BANKNIFTY", "NIFTYNXT50")):
            return c
    return matches[0]


def get_futures_contract_by_expiry(
    contracts: list, expiry: str, inst_types: tuple = ("FUTSTK", "FUTIDX")
) -> dict | None:
    for c in contracts:
        if c.get("pExpiryDate") == expiry and c.get("pInstType") in inst_types:
            return c
    return None


def _render_balance_card(t: dict, req_amount: float = 0):
    try:
        client_bal = _create_kotak_client()
        lim = client_bal.limits(segment="ALL", exchange="ALL", product="ALL")
        ldata = lim if isinstance(lim, dict) else {}
        cash = float(ldata.get("RmsPayInAmt", 0) or 0)
        net = float(ldata.get("Net", 0) or 0)
        avl = cash if cash > 0 else net
        sufficient = avl >= req_amount if req_amount > 0 else True
        bal_color = t["green"] if sufficient else t["red"]
        st.markdown(
            f"""
        <div style="background:{t['card_bg']};border-radius:12px;padding:14px 24px;
                    outline:1px solid {t['card_border']};margin-bottom:16px">
            <div style="display:flex;justify-content:space-between">
                <div style="color:{t['text_muted']};font-size:12px">Available Balance</div>
                <div style="color:{bal_color};font-size:12px;font-weight:700">
                    ₹ {avl:,.2f} {'✓' if sufficient else '✗ Insufficient'}
                </div>
            </div>
        </div>""",
            unsafe_allow_html=True,
        )
    except:
        pass


def _render_price_card(t, px_text, subtitle):
    st.markdown(
        f"""
    <div style="background:{t['card_bg']};border-radius:12px;padding:16px 24px;
                outline:1px solid {t['card_border']};margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <div style="color:{t['text_primary']};font-size:24px;font-weight:700">{px_text}</div>
                <div style="color:{t['text_muted']};font-size:11px;margin-top:2px">{subtitle}</div>
            </div>
            <div style="background:{t['header_bg']};border-radius:8px;padding:6px 14px;
                        font-size:12px;color:{t['text_secondary']}">At Market</div>
        </div>
    </div>""",
        unsafe_allow_html=True,
    )


def _render_order_summary(t, qty, lot_size, lots, value_label, value):
    st.markdown(
        f"""
    <div style="background:{t['card_bg']};border-radius:12px;padding:16px 24px;
                outline:1px solid {t['card_border']};margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;margin-bottom:10px">
            <div style="color:{t['text_muted']};font-size:12px">Quantity</div>
            <div style="color:{t['text_primary']};font-size:12px;font-weight:600">
                {qty} units ({lots} lot × {lot_size})
            </div>
        </div>
        <div style="display:flex;justify-content:space-between;
                    padding-top:10px;border-top:1px solid {t['card_border']}">
            <div style="color:{t['text_muted']};font-size:12px">{value_label}</div>
            <div style="color:{t['text_primary']};font-size:12px;font-weight:700">₹ {value:,.2f}</div>
        </div>
    </div>""",
        unsafe_allow_html=True,
    )


def _render_fo_otp_section(r):
    t = get_theme()
    payload = st.session_state.get("fo_otp_payload", {})
    ctype = payload.get("contract_type", "")
    tag = {
        "FUTURES": "📊 FUTURES",
        "OPTIONS": "🎯 OPTIONS",
        "CURRENCY": "💱 CURRENCY",
        "COMMODITY": "🏭 COMMODITY",
    }.get(ctype, ctype)
    qty_total = payload.get("lots", 1) * payload.get("lot_size", 1)

    st.markdown(
        f"""
    <div style="background:{t['card_bg']};border-radius:12px;padding:16px 24px;
                outline:1px solid {t['card_border']};margin-bottom:16px">
        <div style="color:{t['text_primary']};font-size:14px;font-weight:600;margin-bottom:4px">
            🔐 Confirm {tag} Order
        </div>
        <div style="color:{t['text_muted']};font-size:12px">
            {payload.get('action')} &nbsp;·&nbsp; {payload.get('lots')} lot(s)
            &nbsp;·&nbsp; {payload.get('trading_symbol')} &nbsp;·&nbsp; {qty_total} units
        </div>
    </div>""",
        unsafe_allow_html=True,
    )

    ttl = r.ttl(REDIS_FO_OTP)
    if ttl > 0:
        st.info(f"⏳ OTP valid for **{ttl}** more seconds")
        entered = st.text_input(
            "Enter 6-digit OTP",
            max_chars=6,
            key="fo_otp_input",
            placeholder="e.g. 482910",
        )
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button(
                "✅ Confirm & Place Order",
                use_container_width=True,
                type="primary",
                key="fo_confirm",
            ):
                if not entered:
                    st.error("Please enter the OTP first.")
                else:
                    data, status = verify_fo_otp(r, entered)
                    if status == "ok":
                        seg = data.get("exchange_segment", "nse_fo")
                        with st.spinner(f"Placing {ctype} order..."):
                            order_id, err = place_fo_order(
                                data["trading_symbol"],
                                data["action"],
                                data["lots"],
                                data["lot_size"],
                                seg,
                            )
                        if order_id:
                            save_fo_order(
                                r,
                                data["symbol"],
                                data["trading_symbol"],
                                data["action"],
                                data["lots"],
                                data["lot_size"],
                                data.get("price", 0),
                                order_id,
                                data["contract_type"],
                                seg,
                            )
                            sync_fo_positions(r)
                            st.success(f"✅ {ctype} order placed! ID: `{order_id}`")
                            for k in ["fo_otp_pending", "fo_otp_payload"]:
                                st.session_state.pop(k, None)
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Order failed: {err}")
                            for k in ["fo_otp_pending", "fo_otp_payload"]:
                                st.session_state.pop(k, None)
                    elif status == "expired":
                        st.error("⏰ OTP expired.")
                        st.session_state.pop("fo_otp_pending", None)
                    elif status == "invalid":
                        st.error("❌ Wrong OTP. Try again.")
        with col_cancel:
            if st.button("❌ Cancel", use_container_width=True, key="fo_cancel"):
                r.delete(REDIS_FO_OTP)
                for k in ["fo_otp_pending", "fo_otp_payload"]:
                    st.session_state.pop(k, None)
                st.rerun()
    else:
        st.error("⏰ OTP expired.")
        st.session_state.pop("fo_otp_pending", None)
        payload_backup = payload.copy()
        if st.button("🔁 Resend OTP", use_container_width=True, key="fo_resend"):
            otp = generate_otp()
            store_fo_otp(r, otp, payload_backup)
            send_fo_otp(
                otp,
                payload_backup.get("trading_symbol", ""),
                payload_backup.get("action", ""),
                payload_backup.get("lots", 1),
                payload_backup.get("lot_size", 1),
                payload_backup.get("contract_type", ""),
            )
            st.session_state["fo_otp_pending"] = True
            st.session_state["fo_otp_payload"] = payload_backup
            st.rerun()


def _get_atm_contracts(contracts: list, max_tokens: int = 800, spot_price: float = 0) -> list:
    if not contracts:
        return []

    strikes = []
    for c in contracts:
        strike_raw = c.get("dStrikePrice;", 0) or 0
        strike_val = int(float(strike_raw) / 100)
        if strike_val > 0:
            strikes.append(strike_val)

    if not strikes:
        return contracts[:max_tokens]

    sorted_strikes = sorted(set(strikes))

    if spot_price and spot_price > 0:
        atm_proxy = spot_price
    else:
        atm_proxy = sorted_strikes[len(sorted_strikes) // 2]

    print(f"[ATM PROXY] spot={spot_price} atm_proxy={atm_proxy} total_contracts={len(contracts)}")

    def strike_distance(c):
        sv = int(float(c.get("dStrikePrice;", 0) or 0) / 100)
        return abs(sv - atm_proxy)

    sorted_contracts = sorted(contracts, key=strike_distance)
    return sorted_contracts[:max_tokens]


def _render_futures_tab(
    r,
    t,
    otp_pending,
    tab_key,
    symbols_dict,
    fetch_fn,
    filter_fn,
    exchange_segment,
    contract_type,
    inst_types,
    price_label="Estimated Contract Value",
):
    symbols = sorted(symbols_dict.keys())
    format_fn = lambda x: f"{x} — {symbols_dict.get(x, x)}"

    selected = st.selectbox(
        "🔍 Search & Select",
        options=symbols,
        format_func=format_fn,
        key=f"{tab_key}_selected",
        disabled=otp_pending,
    )

    if st.button("🔍 Load Contracts", key=f"{tab_key}_load", disabled=otp_pending):
        st.session_state[f"{tab_key}_active"] = "futures"
        with st.spinner("Loading contracts and live prices..."):
            contracts_data = fetch_fn(selected)
            prices_data = fetch_contract_prices(contracts_data, exchange_segment)
        st.session_state[f"{tab_key}_contracts"] = contracts_data
        st.session_state[f"{tab_key}_prices"] = prices_data
        st.session_state[f"{tab_key}_symbol"] = selected

    contracts = st.session_state.get(f"{tab_key}_contracts", [])
    if contracts and st.session_state.get(f"{tab_key}_symbol") == selected:
        futures = filter_fn(contracts)
        if not futures:
            st.warning("No futures contracts found.")
            return

        expiries = get_expiries(futures)
        expiry_labels = {e: _format_expiry(e) for e in expiries}
        expiry = st.selectbox(
            "Select Expiry",
            options=expiries,
            format_func=lambda x: expiry_labels.get(x, x),
            key=f"{tab_key}_expiry",
            disabled=otp_pending,
        )

        contract = get_futures_contract_by_expiry(contracts, expiry, inst_types)
        if not contract:
            st.warning("No contract found for this expiry.")
            return

        trd_sym = contract["pTrdSymbol"]
        lot_size = int(contract.get("lLotSize", 1))
        prices = st.session_state.get(f"{tab_key}_prices", {})
        live_px = prices.get(trd_sym)
        px_text = f"₹ {live_px:,.2f}" if (live_px and live_px > 0) else "—"
        px_sub = (
            f"📡 Live (Kotak)"
            if (live_px and live_px > 0)
            else "⚠️ Market Closed / No Data"
        )

        _render_price_card(t, px_text, f"{trd_sym} · Lot {lot_size} · {px_sub}")

        col1, col2 = st.columns([3, 2])
        with col1:
            lots = st.number_input(
                "Number of Lots",
                min_value=1,
                step=1,
                value=1,
                key=f"{tab_key}_lots",
                disabled=otp_pending,
            )
        with col2:
            action = st.radio(
                "Action",
                ["BUY", "SELL"],
                horizontal=True,
                key=f"{tab_key}_action",
                disabled=otp_pending,
            )

        qty = lots * lot_size
        est_val = qty * live_px if (live_px and live_px > 0) else 0

        _render_order_summary(t, qty, lot_size, lots, price_label, est_val)
        _render_balance_card(t, est_val)

        btn = f"{'🟢 BUY' if action == 'BUY' else '🔴 SELL'} · {contract_type} · ₹{est_val:,.2f}"
        if st.button(
            btn,
            use_container_width=True,
            type="primary",
            disabled=otp_pending,
            key=f"{tab_key}_btn",
        ):
            otp = generate_otp()
            payload = {
                "trading_symbol": trd_sym,
                "symbol": selected,
                "action": action,
                "lots": lots,
                "lot_size": lot_size,
                "contract_type": contract_type,
                "exchange_segment": exchange_segment,
                "price": live_px or 0,
            }
            store_fo_otp(r, otp, payload)
            sent = send_fo_otp(otp, trd_sym, action, lots, lot_size, contract_type)
            if sent:
                st.session_state["fo_otp_pending"] = True
                st.session_state["fo_otp_payload"] = payload
                st.rerun()
            else:
                st.error("❌ Failed to send OTP via Telegram.")

    if (
        otp_pending
        and st.session_state.get("fo_otp_payload", {}).get("contract_type")
        == contract_type
        and st.session_state.get("fo_otp_payload", {}).get("exchange_segment")
        == exchange_segment
    ):
        _render_fo_otp_section(r)


def _render_options_tab(
    r,
    t,
    otp_pending,
    tab_key,
    symbols_dict,
    fetch_fn,
    filter_fn,
    exchange_segment,
    contract_type,
):
    symbols = sorted(symbols_dict.keys())
    format_fn = lambda x: f"{x} — {symbols_dict.get(x, x)}"

    selected = st.selectbox(
        "🔍 Search & Select",
        options=symbols,
        format_func=format_fn,
        key=f"{tab_key}_opt_selected",
        disabled=otp_pending,
    )

    if st.button("🔍 Load Contracts", key=f"{tab_key}_opt_load", disabled=otp_pending):
        st.session_state[f"{tab_key}_active"] = "options"
        with st.spinner("Loading contracts and live prices..."):
            contracts_data = fetch_fn(selected)
            spot_px = get_live_price_fo(r, selected) or 0
            if not spot_px:
                try:
                    if contracts_data:
                        spot_px = float(contracts_data[0].get("pScripBasePrice", 0) or 0) / 100
                except:
                    spot_px = 0
            atm_contracts = _get_atm_contracts(contracts_data, max_tokens=800, spot_price=spot_px)
            prices_data = fetch_contract_prices(atm_contracts, exchange_segment)
        st.session_state[f"{tab_key}_opt_contracts"] = contracts_data
        st.session_state[f"{tab_key}_opt_prices"] = prices_data
        st.session_state[f"{tab_key}_opt_symbol"] = selected

    contracts = st.session_state.get(f"{tab_key}_opt_contracts", [])
    if contracts and st.session_state.get(f"{tab_key}_opt_symbol") == selected:
        options = filter_fn(contracts)
        if not options:
            st.warning("No options contracts found.")
            return

        expiries = get_expiries(options)
        expiry_labels = {e: _format_expiry(e) for e in expiries}

        col1, col2 = st.columns(2)
        with col1:
            expiry = st.selectbox(
                "Select Expiry",
                options=expiries,
                format_func=lambda x: expiry_labels.get(x, x),
                key=f"{tab_key}_opt_expiry",
                disabled=otp_pending,
            )
        with col2:
            opt_type = st.radio(
                "CE / PE",
                ["CE", "PE"],
                horizontal=True,
                key=f"{tab_key}_opt_type",
                disabled=otp_pending,
            )

        strikes = get_strikes(options, expiry, opt_type)
        if not strikes:
            st.warning("No strikes available.")
            return

        strike = st.selectbox(
            f"Select Strike Price ({opt_type})",
            strikes,
            key=f"{tab_key}_opt_strike",
            disabled=otp_pending,
        )
        contract = get_contract(options, expiry, opt_type, strike)
        if not contract:
            st.warning("Contract not found.")
            return

        trd_sym = contract["pTrdSymbol"]
        lot_size = int(contract.get("lLotSize", 1))
        prices = st.session_state.get(f"{tab_key}_opt_prices", {})
        live_px = prices.get(trd_sym)
        live_px = live_px if (live_px and live_px > 0) else None
        px_text = f"₹ {live_px:,.2f}" if live_px else "—"
        px_sub = "📡 Live Premium (Kotak)" if live_px else "⚠️ Market Closed / No Data"

        _render_price_card(t, px_text, f"{trd_sym} · Lot {lot_size} · {px_sub}")

        col1, col2 = st.columns([3, 2])
        with col1:
            lots = st.number_input(
                "Number of Lots",
                min_value=1,
                step=1,
                value=1,
                key=f"{tab_key}_opt_lots",
                disabled=otp_pending,
            )
        with col2:
            action = st.radio(
                "Action",
                ["BUY", "SELL"],
                horizontal=True,
                key=f"{tab_key}_opt_action",
                disabled=otp_pending,
            )

        qty = lots * lot_size
        premium_cost = (live_px * qty) if live_px else 0

        spot_px = get_live_price_fo(r, selected)
        spot_line = ""
        if spot_px:
            spot_line = (
                f'<div style="display:flex;justify-content:space-between;margin-top:10px">'
                f'<div style="color:{t["text_muted"]};font-size:12px">Underlying Spot</div>'
                f'<div style="color:{t["text_primary"]};font-size:12px;font-weight:600">₹ {spot_px:,.2f}</div>'
                f"</div>"
            )

        st.markdown(
            f"""
        <div style="background:{t['card_bg']};border-radius:12px;padding:16px 24px;
                    outline:1px solid {t['card_border']};margin-bottom:16px">
            <div style="display:flex;justify-content:space-between;margin-bottom:10px">
                <div style="color:{t['text_muted']};font-size:12px">Quantity</div>
                <div style="color:{t['text_primary']};font-size:12px;font-weight:600">
                    {qty} units ({lots} lot × {lot_size})
                </div>
            </div>
            <div style="display:flex;justify-content:space-between;
                        padding-top:10px;border-top:1px solid {t['card_border']}">
                <div style="color:{t['text_muted']};font-size:12px">Premium Cost</div>
                <div style="color:{t['text_primary']};font-size:12px;font-weight:700">₹ {premium_cost:,.2f}</div>
            </div>
            {spot_line}
        </div>""",
            unsafe_allow_html=True,
        )

        _render_balance_card(t, premium_cost)

        btn = f"{'🟢 BUY' if action == 'BUY' else '🔴 SELL'} · {opt_type} · ₹{premium_cost:,.2f}"
        if st.button(
            btn,
            use_container_width=True,
            type="primary",
            disabled=otp_pending,
            key=f"{tab_key}_opt_btn",
        ):
            otp = generate_otp()
            payload = {
                "trading_symbol": trd_sym,
                "symbol": selected,
                "action": action,
                "lots": lots,
                "lot_size": lot_size,
                "contract_type": contract_type,
                "exchange_segment": exchange_segment,
                "opt_type": opt_type,
                "strike": strike,
                "price": live_px or 0,
            }
            store_fo_otp(r, otp, payload)
            sent = send_fo_otp(otp, trd_sym, action, lots, lot_size, contract_type)
            if sent:
                st.session_state["fo_otp_pending"] = True
                st.session_state["fo_otp_payload"] = payload
                st.rerun()
            else:
                st.error("❌ Failed to send OTP via Telegram.")

    if (
        otp_pending
        and st.session_state.get("fo_otp_payload", {}).get("contract_type")
        == contract_type
        and st.session_state.get("fo_otp_payload", {}).get("exchange_segment")
        == exchange_segment
    ):
        _render_fo_otp_section(r)


def render_fo_page(r):
    t = get_theme()
    otp_pending = st.session_state.get("fo_otp_pending", False)

    st.markdown(
        f"""
    <div style="background:#f0faf5;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                border-left:3px solid #1ba572;font-size:12px;color:#0a4a2a">
        📈 <b>F&amp;O Trading</b> — NSE &amp; BSE Futures/Options · Currency (CDS) · Commodity (MCX)
        · Product: NRML (overnight positions).
    </div>""",
        unsafe_allow_html=True,
    )

    fo_stocks = load_fo_stocks()
    fo_bse_stocks = load_fo_bse_stocks()

    if not fo_stocks:
        st.error("config_fo.json not found.")
        return

    tab_nse, tab_bse, tab_cur, tab_com, tab_pos = st.tabs(
        [
            "📊 NSE F&O",
            "📈 BSE F&O",
            "💱 Currency",
            "🏭 Commodity",
            "📋 Positions",
        ]
    )

    with tab_nse:
        nse_sub_fut, nse_sub_opt = st.tabs(["Futures", "Options"])

        with nse_sub_fut:
            st.markdown(
                f"""
            <div style="background:#fff8e6;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                        border-left:3px solid #ff9800;font-size:12px;color:#7a5a00">
                📊 <b>NSE Futures</b> — Index &amp; Stock futures. NRML overnight.
            </div>""",
                unsafe_allow_html=True,
            )
            _render_futures_tab(
                r, t, otp_pending, "nse_fut", fo_stocks,
                fetch_contracts, get_futures_nse, "nse_fo", "FUTURES", ("FUTSTK", "FUTIDX"),
            )

        with nse_sub_opt:
            st.markdown(
                f"""
            <div style="background:#fff3f3;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                        border-left:3px solid #e34a3a;font-size:12px;color:#7a1a1a">
                🎯 <b>NSE Options</b> — CE (calls) and PE (puts). Premium paid upfront.
            </div>""",
                unsafe_allow_html=True,
            )
            _render_options_tab(
                r, t, otp_pending, "nse_opt", fo_stocks,
                fetch_contracts, get_options_nse, "nse_fo", "OPTIONS",
            )

    with tab_bse:
        if not fo_bse_stocks:
            st.warning("config_fo_bse.json not found. Run generate_fo_bse_config.py first.")
        else:
            bse_sub_fut, bse_sub_opt = st.tabs(["Futures", "Options"])

            with bse_sub_fut:
                st.markdown(
                    f"""
                <div style="background:#fff8e6;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                            border-left:3px solid #ff9800;font-size:12px;color:#7a5a00">
                    📈 <b>BSE Futures</b> — SENSEX, BANKEX &amp; stock futures. NRML overnight.
                </div>""",
                    unsafe_allow_html=True,
                )
                _render_futures_tab(
                    r, t, otp_pending, "bse_fut", fo_bse_stocks,
                    fetch_contracts_bse, get_futures_bse, "bse_fo", "FUTURES", ("SF", "IF"),
                )

            with bse_sub_opt:
                st.markdown(
                    f"""
                <div style="background:#fff3f3;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                            border-left:3px solid #e34a3a;font-size:12px;color:#7a1a1a">
                    🎯 <b>BSE Options</b> — CE/PE on BSE stocks &amp; indices.
                </div>""",
                    unsafe_allow_html=True,
                )
                _render_options_tab(
                    r, t, otp_pending, "bse_opt", fo_bse_stocks,
                    fetch_contracts_bse, get_options_bse, "bse_fo", "OPTIONS",
                )

    with tab_cur:
        cur_sub_fut, cur_sub_opt = st.tabs(["Futures", "Options"])

        with cur_sub_fut:
            st.markdown(
                f"""
            <div style="background:#f0f4ff;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                        border-left:3px solid #3b6fd4;font-size:12px;color:#1a2a6a">
                💱 <b>Currency Futures</b> — USDINR, EURINR, GBPINR, JPYINR &amp; more.
                Lot size = 1000 units. NRML product.
            </div>""",
                unsafe_allow_html=True,
            )
            _render_futures_tab(
                r, t, otp_pending, "cur_fut", CURRENCY_SYMBOLS,
                fetch_contracts_currency, get_futures_currency, "cde_fo", "CURRENCY",
                ("FUTCUR",), price_label="Estimated Contract Value",
            )

        with cur_sub_opt:
            st.markdown(
                f"""
            <div style="background:#f0f4ff;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                        border-left:3px solid #3b6fd4;font-size:12px;color:#1a2a6a">
                💱 <b>Currency Options</b> — CE/PE on currency pairs. Premium paid upfront.
            </div>""",
                unsafe_allow_html=True,
            )
            _render_options_tab(
                r, t, otp_pending, "cur_opt", CURRENCY_SYMBOLS,
                fetch_contracts_currency, get_options_currency, "cde_fo", "CURRENCY",
            )

    with tab_com:
        st.markdown(
            f"""
        <div style="background:#fdf5e6;border-radius:8px;padding:10px 14px;margin-bottom:12px;
                    border-left:3px solid #c47a1e;font-size:12px;color:#5a3a00">
            🏭 <b>Commodity Futures (MCX)</b> — Gold, Silver, Crude Oil, Natural Gas &amp; more.
            NRML product. Futures only.
        </div>""",
            unsafe_allow_html=True,
        )
        _render_futures_tab(
            r, t, otp_pending, "com_fut", COMMODITY_SYMBOLS,
            fetch_contracts_commodity, lambda c: c, "mcx_fo", "COMMODITY",
            ("FUTCOM", "FUTCOMDTY"), price_label="Estimated Contract Value",
        )

    with tab_pos:
        col_sync, col_last = st.columns([1, 5])
        with col_sync:
            if st.button("🔄 Sync", key="fo_sync", use_container_width=True):
                with st.spinner("Syncing F&O positions..."):
                    sync_fo_positions(r)
                st.rerun()
        with col_last:
            last = r.get(REDIS_FO_LAST_SYNC)
            if last:
                st.caption(f"Last synced: {last[:19].replace('T',' ')} IST")

        raw = r.hgetall(REDIS_FO_POSITIONS)
        positions = [json.loads(v) for v in raw.values()] if raw else []

        st.markdown(
            f"<div style='margin-top:14px;color:{t['text_primary']};font-size:18px;"
            f"font-weight:700;margin-bottom:8px'>📋 Open Positions ({len(positions)})</div>",
            unsafe_allow_html=True,
        )

        if positions:
            rows_html = ""
            for p in positions:
                sym = p.get("symbol", "")
                qty = p.get("qty", 0)
                avg = float(p.get("avg_price", 0))
                ltp = float(p.get("ltp", 0))
                pnl = float(p.get("pnl", 0))
                product = p.get("product", "")
                seg = p.get("segment", "")
                pc = t["green"] if pnl >= 0 else t["red"]
                ps = "+" if pnl >= 0 else ""
                seg_badge = {
                    "nse_fo": "NSE",
                    "bse_fo": "BSE",
                    "cde_fo": "CDS",
                    "mcx_fo": "MCX",
                }.get(seg.lower(), seg.upper())
                rows_html += f"""
                <tr class="holdings-row" style="border-bottom:1px solid {t['card_border']}">
                    <td style="padding:12px 16px">
                        <div style="font-weight:600;color:{t['text_primary']};font-size:13px">{sym}</div>
                        <div style="color:{t['text_muted']};font-size:11px;margin-top:2px">
                            {qty} units · Avg ₹{avg:,.2f}
                        </div>
                        <div style="margin-top:4px;display:flex;gap:5px">
                            <span style="background:#ff9800;color:#fff;font-size:9px;
                                         font-weight:600;padding:1px 6px;border-radius:3px">{product}</span>
                            <span style="background:{t['exch_bg']};color:{t['exch_text']};font-size:9px;
                                         padding:1px 6px;border-radius:3px">{seg_badge}</span>
                        </div>
                    </td>
                    <td style="padding:12px 16px;text-align:right;color:{t['text_primary']};
                               font-weight:600;font-size:14px">₹{ltp:,.2f}</td>
                    <td style="padding:12px 16px;text-align:right">
                        <div style="color:{pc};font-weight:700;font-size:14px">{ps}₹{pnl:,.2f}</div>
                    </td>
                </tr>"""
            st.markdown(
                f"""
            <div style="background:{t['card_bg']};border-radius:10px;overflow:hidden;
                        outline:1px solid {t['card_border']};margin-bottom:14px">
                <table style="width:100%;border-collapse:collapse">
                    <thead>
                        <tr style="background:{t['header_bg']}">
                            <th style="padding:10px 16px;text-align:left;color:{t['text_muted']};
                                       font-size:11px;font-weight:500">SYMBOL</th>
                            <th style="padding:10px 16px;text-align:right;color:{t['text_muted']};
                                       font-size:11px;font-weight:500">LTP</th>
                            <th style="padding:10px 16px;text-align:right;color:{t['text_muted']};
                                       font-size:11px;font-weight:500">P&amp;L</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>""",
                unsafe_allow_html=True,
            )
        else:
            st.caption("📭 No F&O positions. Click Sync.")

        orders = get_fo_orders(r)
        st.markdown(
            f"<div style='margin-top:22px;color:{t['text_primary']};font-size:18px;"
            f"font-weight:700;margin-bottom:8px'>📜 F&amp;O Order History</div>",
            unsafe_allow_html=True,
        )
        if orders:
            order_rows_html = ""
            for o in orders:
                t_str = o.get("time", "")[:19].replace("T", " ")
                sym = o.get("trading_symbol", "")
                ctype = o.get("contract_type", "")
                seg = o.get("segment", "nse_fo")
                act = o.get("action", "")
                act_col = t["green"] if act == "BUY" else t["red"]
                lots = o.get("lots", "")
                o_qty = o.get("quantity", "")
                ord_id = o.get("order_id", "")
                seg_lbl = {
                    "nse_fo": "NSE", "bse_fo": "BSE",
                    "cde_fo": "CDS", "mcx_fo": "MCX",
                }.get(seg.lower(), seg.upper())
                order_rows_html += f"""
                <tr class="holdings-row" style="border-bottom:1px solid {t['card_border']}">
                    <td style="padding:9px 12px;color:{t['text_secondary']};font-size:12px">{t_str}</td>
                    <td style="padding:9px 12px;color:{t['text_primary']};font-weight:600;font-size:13px">{sym}</td>
                    <td style="padding:9px 12px;text-align:center;color:{t['text_secondary']};font-size:12px">{ctype}</td>
                    <td style="padding:9px 12px;text-align:center;color:{t['text_secondary']};font-size:12px">{seg_lbl}</td>
                    <td style="padding:9px 12px;text-align:center;color:{act_col};font-weight:600;font-size:12px">{act}</td>
                    <td style="padding:9px 12px;text-align:right;color:{t['text_secondary']};font-size:13px">{lots}</td>
                    <td style="padding:9px 12px;text-align:right;color:{t['text_secondary']};font-size:13px">{o_qty}</td>
                    <td style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px">{ord_id}</td>
                </tr>"""
            st.markdown(
                f"""
            <div style="background:{t['card_bg']};border-radius:10px;overflow:hidden;
                        outline:1px solid {t['card_border']};margin-bottom:14px">
                <table style="width:100%;border-collapse:collapse">
                    <thead>
                        <tr style="background:{t['header_bg']}">
                            <th style="padding:9px 12px;text-align:left;color:{t['text_muted']};font-size:11px;font-weight:500">TIME</th>
                            <th style="padding:9px 12px;text-align:left;color:{t['text_muted']};font-size:11px;font-weight:500">SYMBOL</th>
                            <th style="padding:9px 12px;text-align:center;color:{t['text_muted']};font-size:11px;font-weight:500">TYPE</th>
                            <th style="padding:9px 12px;text-align:center;color:{t['text_muted']};font-size:11px;font-weight:500">EXCH</th>
                            <th style="padding:9px 12px;text-align:center;color:{t['text_muted']};font-size:11px;font-weight:500">ACTION</th>
                            <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">LOTS</th>
                            <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">QTY</th>
                            <th style="padding:9px 12px;text-align:right;color:{t['text_muted']};font-size:11px;font-weight:500">ORDER ID</th>
                        </tr>
                    </thead>
                    <tbody>{order_rows_html}</tbody>
                </table>
            </div>""",
                unsafe_allow_html=True,
            )
        else:
            st.caption("📭 No F&O orders placed yet.")
