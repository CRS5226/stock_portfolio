import json
import pandas as pd

from config import REDIS_PREFIX_5M, REDIS_PREFIX_1D
from auth.kotak_client import _create_kotak_client


def get_live_price(r, symbol):
    for prefix in (REDIS_PREFIX_5M, REDIS_PREFIX_1D):
        key = f"{prefix}:{symbol}"
        if r.exists(key):
            try:
                latest = max(r.hkeys(key), key=lambda x: pd.to_datetime(x))
                row = json.loads(r.hget(key, latest))
                price = row.get("Close") or row.get("close")
                if price:
                    return float(price)
            except:
                pass
    return None


def get_live_price_kotak(instrument_token, exchange_segment):
    if not instrument_token or instrument_token == 0:
        return None
    try:
        client = _create_kotak_client()
        resp = client.quotes(
            instrument_tokens=[
                {
                    "instrument_token": str(instrument_token),
                    "exchange_segment": exchange_segment,
                }
            ],
            quote_type="ltp",
        )
        if isinstance(resp, list) and resp:
            ltp = resp[0].get("ltp") or resp[0].get("last_traded_price")
            if ltp and float(ltp) > 0:
                return float(ltp)
    except Exception as e:
        print(f"[KOTAK PRICE ERROR] {e}")
    return None


def get_price_with_fallback(r, symbol, instrument_token=0, exchange_segment="nse_cm"):
    price = get_live_price_kotak(instrument_token, exchange_segment)
    if price:
        return price, "kotak"
    return None, None


def get_margin_required(instrument_token, exchange_segment, qty):
    try:
        client = _create_kotak_client()
        resp = client.margin_required(
            exchange_segment=exchange_segment,
            price="0",
            order_type="MKT",
            product="MTF",
            quantity=str(qty),
            instrument_token=str(instrument_token),
            transaction_type="B",
        )
        if isinstance(resp, dict):
            data = resp.get("data", resp)
            if isinstance(data, dict):
                margin = (
                    data.get("ordMrgn")
                    or data.get("marginRequired")
                    or data.get("totalMarginRequired")
                    or data.get("margin")
                    or data.get("total")
                )
                if margin and float(margin) > 0:
                    return float(margin)
        return None
    except Exception as e:
        print(f"[MARGIN ERROR] {e}")
        return None


def get_margin_required_mis(instrument_token, exchange_segment, qty):
    try:
        client = _create_kotak_client()
        resp = client.margin_required(
            exchange_segment=exchange_segment,
            price="0",
            order_type="MKT",
            product="MIS",
            quantity=str(qty),
            instrument_token=str(instrument_token),
            transaction_type="B",
        )
        if isinstance(resp, dict):
            data = resp.get("data", resp)
            if isinstance(data, dict):
                margin = (
                    data.get("ordMrgn")
                    or data.get("marginRequired")
                    or data.get("totalMarginRequired")
                    or data.get("margin")
                    or data.get("total")
                )
                if margin and float(margin) > 0:
                    return float(margin)
        return None
    except Exception as e:
        print(f"[MIS MARGIN ERROR] {e}")
        return None


def get_live_price_fo(r, symbol):
    for prefix in ("ETF_5M", "ETF_1D"):
        key = f"{prefix}:{symbol}"
        if r.exists(key):
            try:
                latest = max(r.hkeys(key), key=lambda x: pd.to_datetime(x))
                row = json.loads(r.hget(key, latest))
                price = row.get("Close") or row.get("close")
                if price:
                    return float(price)
            except:
                pass
    return None
