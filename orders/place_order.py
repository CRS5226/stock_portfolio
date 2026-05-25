import json
from datetime import datetime

from config import (
    INDIA_TZ,
    REDIS_CNC_ORDER_PFX,
    REDIS_MTF_ORDER_PFX,
    REDIS_MIS_ORDER_PFX,
    REDIS_CO_ORDER_PFX,
    REDIS_BO_ORDER_PFX,
    REDIS_FO_ORDER_PFX,
)
from auth.kotak_client import _create_kotak_client


def place_order(
    symbol,
    action,
    qty,
    order_type,
    exchange="NSE",
    trading_symbol=None,
    order_kind="MKT",
    limit_price=0.0,
    trigger_price=0.0,
    co_stop_loss=0.0,
    bo_entry=0.0,
    bo_stoploss=0.0,
    bo_target=0.0,
):
    try:
        client = _create_kotak_client()
        exch_seg = "bse_cm" if exchange == "BSE" else "nse_cm"
        trd_sym = trading_symbol or (symbol if exchange == "BSE" else f"{symbol}-EQ")
        order_kind_to_use = order_kind
        tag_value = None

        if order_type == "CO":
            exch_seg = "nse_cm"
            order_kind_to_use = "L"
            price_str = str(limit_price) if limit_price > 0 else "0"
            trigger_str = str(co_stop_loss)
        elif order_type == "BO":
            exch_seg = "nse_cm"
            order_kind_to_use = "L"
            price_str = str(bo_entry)
            trigger_str = str(bo_stoploss)
            tag_value = f"BO_TGT_{bo_target}"
        elif order_kind == "MKT":
            price_str = "0"
            trigger_str = "0"
        elif order_kind == "L":
            price_str = str(limit_price)
            trigger_str = "0"
        elif order_kind == "SL":
            price_str = str(limit_price)
            trigger_str = str(trigger_price)
        elif order_kind == "SL-M":
            price_str = "0"
            trigger_str = str(trigger_price)
        else:
            price_str = "0"
            trigger_str = "0"

        resp = client.place_order(
            exchange_segment=exch_seg,
            product=order_type,
            price=price_str,
            order_type=order_kind_to_use,
            quantity=str(qty),
            validity="DAY",
            trading_symbol=trd_sym,
            transaction_type="B" if action == "BUY" else "S",
            amo="NO",
            disclosed_quantity="0",
            market_protection="0",
            pf="N",
            trigger_price=trigger_str,
            tag=tag_value,
        )
        print(f"[ORDER RAW] {resp}")
        if isinstance(resp, dict):
            order_id = resp.get("nOrdNo") or resp.get("orderId")
            if order_id:
                return order_id, None
            data = resp.get("data", {})
            if isinstance(data, dict):
                order_id = data.get("nOrdNo") or data.get("orderId")
                if order_id:
                    return order_id, None
            err = resp.get("errMsg") or resp.get("message") or str(resp)
            return None, err
        return None, str(resp)
    except Exception as e:
        err = str(e)
        if "margin" in err.lower() or "insufficient" in err.lower():
            return None, "Insufficient funds — check available margin in Kotak Neo."
        elif "unauthorized" in err.lower():
            return None, "Session expired — please restart the app."
        elif "quantity" in err.lower():
            return None, f"Invalid quantity: {err}"
        return None, err


def save_order_history(
    r,
    symbol,
    action,
    qty,
    price,
    order_id,
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
    ts = datetime.now(INDIA_TZ).isoformat()
    pfx = {
        "CNC": REDIS_CNC_ORDER_PFX,
        "MTF": REDIS_MTF_ORDER_PFX,
        "MIS": REDIS_MIS_ORDER_PFX,
        "CO":  REDIS_CO_ORDER_PFX,
        "BO":  REDIS_BO_ORDER_PFX,
    }.get(order_type, REDIS_CNC_ORDER_PFX)
    r.set(
        f"{pfx}{ts}",
        json.dumps(
            {
                "symbol": symbol,
                "action": action,
                "qty": qty,
                "price": price,
                "order_id": order_id,
                "order_type": order_type,
                "exchange": exchange,
                "order_kind": order_kind,
                "limit_price": limit_price,
                "trigger_price": trigger_price,
                "co_stop_loss": co_stop_loss,
                "bo_entry": bo_entry,
                "bo_stoploss": bo_stoploss,
                "bo_target": bo_target,
                "broker": "KOTAK",
                "time": ts,
            }
        ),
    )


def get_order_history(r, limit=50):
    orders = []
    for pfx in [
        REDIS_CNC_ORDER_PFX,
        REDIS_MTF_ORDER_PFX,
        REDIS_MIS_ORDER_PFX,
        REDIS_CO_ORDER_PFX,
        REDIS_BO_ORDER_PFX,
    ]:
        for k in r.keys(f"{pfx}*"):
            try:
                orders.append(json.loads(r.get(k)))
            except:
                pass
    orders.sort(key=lambda x: x.get("time", ""), reverse=True)
    return orders[:limit]


def place_fo_order(trading_symbol, action, lots, lot_size, exchange_segment="nse_fo"):
    try:
        client = _create_kotak_client()
        quantity = lots * lot_size
        resp = client.place_order(
            exchange_segment=exchange_segment,
            product="NRML",
            price="0",
            order_type="MKT",
            quantity=str(quantity),
            validity="DAY",
            trading_symbol=trading_symbol,
            transaction_type="B" if action == "BUY" else "S",
            amo="NO",
            disclosed_quantity="0",
            market_protection="0",
            pf="N",
            trigger_price="0",
            tag=None,
        )
        print(f"[FO ORDER RAW] {resp}")
        if isinstance(resp, dict):
            order_id = resp.get("nOrdNo") or resp.get("orderId")
            if order_id:
                return order_id, None
            data = resp.get("data", {})
            if isinstance(data, dict):
                order_id = data.get("nOrdNo") or data.get("orderId")
                if order_id:
                    return order_id, None
            err = resp.get("errMsg") or resp.get("message") or str(resp)
            return None, err
        return None, str(resp)
    except Exception as e:
        err = str(e)
        if "margin" in err.lower() or "insufficient" in err.lower():
            return None, "Insufficient margin — check available funds."
        elif "unauthorized" in err.lower():
            return None, "Session expired — please restart the app."
        return None, err


def save_fo_order(
    r,
    symbol,
    trading_symbol,
    action,
    lots,
    lot_size,
    price,
    order_id,
    contract_type,
    segment="nse_fo",
):
    ts = datetime.now(INDIA_TZ).isoformat()
    r.set(
        f"{REDIS_FO_ORDER_PFX}{ts}",
        json.dumps(
            {
                "symbol": symbol,
                "trading_symbol": trading_symbol,
                "action": action,
                "lots": lots,
                "lot_size": lot_size,
                "quantity": lots * lot_size,
                "price": price,
                "order_id": order_id,
                "contract_type": contract_type,
                "segment": segment,
                "broker": "KOTAK",
                "time": ts,
            }
        ),
    )


def get_fo_orders(r, limit=50):
    keys = sorted(r.keys(f"{REDIS_FO_ORDER_PFX}*"), reverse=True)[:limit]
    orders = []
    for k in keys:
        try:
            orders.append(json.loads(r.get(k)))
        except:
            pass
    return orders
