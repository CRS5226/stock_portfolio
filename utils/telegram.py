import json
import requests
import streamlit as st

from config import TELEGRAM_BOT_TOKEN, CHAT_IDS_FILE, OTP_EXPIRY_SEC


def get_chat_ids():
    import os
    if not os.path.exists(CHAT_IDS_FILE):
        return []
    with open(CHAT_IDS_FILE) as f:
        data = json.load(f)
    return list(data.keys())


def send_telegram_otp(
    otp,
    symbol,
    action,
    qty,
    price,
    order_type,
    exchange="NSE",
    order_kind="MKT",
    limit_price=0.0,
    trigger_price=0.0,
    co_stop_loss=0.0,
    bo_entry=0.0,
    bo_stoploss=0.0,
    bo_target=0.0,
):
    chat_ids = get_chat_ids()
    if not chat_ids:
        return False
    tags = {
        "CNC": "📦 CNC (Long Term)",
        "MTF": "💳 MTF (Margin)",
        "MIS": "⚡ MIS (Intraday)",
        "CO":  "🛡️ CO (Cover Order)",
        "BO":  "🎯 BO (Bracket Order)",
    }
    order_kind_labels = {
        "MKT": "Market",
        "L": f"Limit @ ₹{limit_price}",
        "SL": f"SL Limit — Trigger ₹{trigger_price} / Limit ₹{limit_price}",
        "SL-M": f"SL Market — Trigger ₹{trigger_price}",
    }
    extra_lines = ""
    if order_type == "CO":
        extra_lines = f"Stop-Loss: `₹ {co_stop_loss}`\n"
    elif order_type == "BO":
        extra_lines = (
            f"Entry    : `₹ {bo_entry}`\n"
            f"Stop-Loss: `₹ {bo_stoploss}`\n"
            f"Target   : `₹ {bo_target}`\n"
        )

    msg = (
        f"🔐 *ORDER CONFIRMATION OTP*\n\nOTP: `{otp}`\n\n"
        f"Type     : `{tags.get(order_type, order_type)}`\n"
        f"Exchange : `{exchange}`\n"
        f"Order    : `{order_kind_labels.get(order_kind, order_kind)}`\n"
        f"Action   : `{action}`\nStock  : `{symbol}`\n"
        f"Qty    : `{qty}`\nPrice  : `₹ {price}`\n"
        f"{extra_lines}"
        f"\n⏳ Expires in {OTP_EXPIRY_SEC} seconds\n⚠️ Do not share this OTP."
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    success = True
    last_err = None
    for chat_id in chat_ids:
        try:
            resp = requests.post(
                url,
                json={"chat_id": chat_id, "text": msg},
                timeout=5,
            )
            print(f"[TELEGRAM RESP] chat={chat_id} status={resp.status_code} body={resp.text[:300]}")
            if resp.status_code != 200:
                success = False
                last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")
            success = False
            last_err = str(e)
    try:
        st.session_state["_last_tg_err"] = last_err
    except Exception:
        pass
    return success


def send_fo_otp(otp, trading_symbol, action, lots, lot_size, contract_type):
    chat_ids = get_chat_ids()
    if not chat_ids:
        return False
    tag = {
        "FUTURES": "📊 FUTURES",
        "OPTIONS": "🎯 OPTIONS",
        "CURRENCY": "💱 CURRENCY",
        "COMMODITY": "🏭 COMMODITY",
    }.get(contract_type, contract_type)
    qty = lots * lot_size
    msg = (
        f"🔐 *F&O ORDER OTP*\n\nOTP: `{otp}`\n\n"
        f"Type   : `{tag}`\nAction : `{action}`\n"
        f"Symbol : `{trading_symbol}`\nLots   : `{lots}` × {lot_size} = `{qty} units`\n\n"
        f"⏳ Expires in {OTP_EXPIRY_SEC} seconds\n⚠️ Do not share this OTP."
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    success = True
    for chat_id in chat_ids:
        try:
            resp = requests.post(
                url,
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=5,
            )
            if resp.status_code != 200:
                success = False
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")
            success = False
    return success
