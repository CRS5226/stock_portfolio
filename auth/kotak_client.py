import os
import json
import threading
import redis
import pyotp
import streamlit as st
from neo_api_client import NeoAPI

from config import (
    KOTAK_CONSUMER_KEY,
    KOTAK_MOBILE,
    KOTAK_MPIN,
    KOTAK_UCC,
    KOTAK_TOTP_SECRET,
    CONFIG_FILES_MTF_MIS,
    CONFIG_NSE,
    CONFIG_BSE,
)

# ---------------------------------------------------------------------------
# Thread-safe Kotak singleton — ONE login for the entire process lifetime.
# Every call to _create_kotak_client() performs a fresh TOTP login which
# invalidates ALL other active Kotak sessions. Use get_kotak() everywhere.
# ---------------------------------------------------------------------------
_kotak_lock = threading.Lock()
_kotak_instance = None


@st.cache_resource
def get_redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=int(os.getenv("REDIS_DB", 0)),
        decode_responses=True,
    )


def get_kotak():
    """Return the shared Kotak NeoAPI singleton (thread-safe, process-wide)."""
    global _kotak_instance
    if _kotak_instance is not None:
        return _kotak_instance
    with _kotak_lock:
        if _kotak_instance is None:
            _kotak_instance = _create_kotak_client()
    return _kotak_instance


def refresh_kotak():
    """Force a fresh TOTP re-login. Only call when the session is confirmed expired."""
    global _kotak_instance
    with _kotak_lock:
        _kotak_instance = _create_kotak_client()
    return _kotak_instance


def _create_kotak_client():
    """Internal: performs the actual TOTP login. Do NOT call directly — use get_kotak()."""
    client = NeoAPI(
        environment="prod",
        access_token=None,
        neo_fin_key=None,
        consumer_key=KOTAK_CONSUMER_KEY,
    )
    totp = pyotp.TOTP(KOTAK_TOTP_SECRET).now()
    client.totp_login(mobile_number=KOTAK_MOBILE, ucc=KOTAK_UCC, totp=totp)
    client.totp_validate(mpin=KOTAK_MPIN)
    return client


@st.cache_data(ttl=300)
def load_stocks_mtf_mis():
    stocks = {}
    for cfg in CONFIG_FILES_MTF_MIS:
        if not os.path.exists(cfg):
            continue
        with open(cfg) as f:
            data = json.load(f)
        for s in data.get("stocks", []):
            code = s.get("stock_code", "").strip()
            if code:
                stocks[code] = s.get("name", code)
    return stocks


@st.cache_data(ttl=3600)
def load_stocks_nse():
    if not os.path.exists(CONFIG_NSE):
        return {}
    with open(CONFIG_NSE) as f:
        data = json.load(f)
    return {
        s["stock_code"]: {
            "name": s.get("name", s["stock_code"]),
            "trading_symbol": s.get("trading_symbol", f"{s['stock_code']}-EQ"),
            "instrument_token": s.get("instrument_token", 0),
            "lot_size": s.get("lot_size", 1),
        }
        for s in data.get("stocks", [])
        if s.get("stock_code")
    }


@st.cache_data(ttl=3600)
def load_stocks_bse():
    if not os.path.exists(CONFIG_BSE):
        return {}
    with open(CONFIG_BSE) as f:
        data = json.load(f)
    return {
        s["stock_code"]: {
            "name": s.get("name", s["stock_code"]),
            "trading_symbol": s.get("trading_symbol", s["stock_code"]),
            "instrument_token": s.get("instrument_token", 0),
            "lot_size": s.get("lot_size", 1),
        }
        for s in data.get("stocks", [])
        if s.get("stock_code")
    }
