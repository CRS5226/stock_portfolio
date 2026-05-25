import json
import random
from datetime import datetime

from config import INDIA_TZ, OTP_EXPIRY_SEC, REDIS_OTP_PENDING, REDIS_FO_OTP


def generate_otp():
    return str(random.randint(100000, 999999))


def store_otp(
    r,
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
    r.setex(
        REDIS_OTP_PENDING,
        OTP_EXPIRY_SEC,
        json.dumps(
            {
                "otp": otp,
                "symbol": symbol,
                "action": action,
                "qty": qty,
                "price": price,
                "order_type": order_type,
                "exchange": exchange,
                "order_kind": order_kind,
                "limit_price": limit_price,
                "trigger_price": trigger_price,
                "co_stop_loss": co_stop_loss,
                "bo_entry": bo_entry,
                "bo_stoploss": bo_stoploss,
                "bo_target": bo_target,
                "created": datetime.now(INDIA_TZ).isoformat(),
            }
        ),
    )


def verify_otp(r, entered_otp):
    raw = r.get(REDIS_OTP_PENDING)
    if not raw:
        return None, "expired"
    data = json.loads(raw)
    if data["otp"] == str(entered_otp).strip():
        r.delete(REDIS_OTP_PENDING)
        return data, "ok"
    return None, "invalid"


def store_fo_otp(r, otp, payload: dict):
    r.setex(
        REDIS_FO_OTP,
        OTP_EXPIRY_SEC,
        json.dumps(
            {**payload, "otp": otp, "created": datetime.now(INDIA_TZ).isoformat()}
        ),
    )


def verify_fo_otp(r, entered: str):
    raw = r.get(REDIS_FO_OTP)
    if not raw:
        return None, "expired"
    data = json.loads(raw)
    if data["otp"] == str(entered).strip():
        r.delete(REDIS_FO_OTP)
        return data, "ok"
    return None, "invalid"
