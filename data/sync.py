import json
import time
from datetime import datetime

from config import (
    INDIA_TZ,
    SYNC_INTERVAL,
    REDIS_CNC_HOLDINGS,
    REDIS_CNC_LAST_SYNC,
    REDIS_MTF_POSITIONS,
    REDIS_MTF_LAST_SYNC,
    REDIS_FO_POSITIONS,
    REDIS_FO_LAST_SYNC,
)
from auth.kotak_client import _create_kotak_client


def sync_cnc(r):
    try:
        client = _create_kotak_client()
        resp = client.holdings()
        holdings = []
        if isinstance(resp, dict):
            raw = resp.get("data", [])
            if isinstance(raw, list):
                holdings = raw
        mtf_symbols = set()
        try:
            pos_resp = client.positions()
            pos_items = (
                pos_resp.get("data", [])
                if isinstance(pos_resp, dict)
                else (pos_resp if isinstance(pos_resp, list) else [])
            )
            mtf_symbols = {
                p.get("sym", "").strip()
                for p in pos_items
                if p.get("prod", "").upper() == "MTF"
            }
        except Exception as pe:
            print(f"[SYNC CNC] MTF tag error: {pe}")
        r.delete(REDIS_CNC_HOLDINGS)
        if holdings:
            pipe = r.pipeline()
            for h in holdings:
                symbol = (h.get("symbol") or h.get("displaySymbol") or "").strip()
                if not symbol:
                    continue
                product_type = "MTF" if symbol in mtf_symbols else "CNC"
                pipe.hset(
                    REDIS_CNC_HOLDINGS,
                    symbol,
                    json.dumps(
                        {
                            "symbol": symbol,
                            "quantity": int(h.get("quantity", 0) or 0),
                            "average_price": float(h.get("averagePrice", 0) or 0),
                            "last_price": float(h.get("closingPrice", 0) or 0),
                            "pnl": float(h.get("unrealisedGainLoss", 0) or 0),
                            "product_type": product_type,
                            "instrument_token": int(h.get("instrumentToken", 0) or 0),
                            "exchange_identifier": int(
                                h.get("exchangeIdentifier", 0) or 0
                            ),
                            "exchange": (
                                "BSE"
                                if h.get("exchangeSegment", "") == "bse_cm"
                                else "NSE"
                            ),
                            "synced_at": datetime.now(INDIA_TZ).isoformat(),
                        }
                    ),
                )
            pipe.execute()
        r.set(REDIS_CNC_LAST_SYNC, datetime.now(INDIA_TZ).isoformat())
        print(f"[SYNC CNC] {len(holdings)} holdings — MTF: {mtf_symbols}")
        return True
    except Exception as e:
        print(f"[SYNC CNC ERROR] {e}")
        return False


def sync_mtf(r):
    try:
        client = _create_kotak_client()
        resp = client.positions()
        items = (
            resp.get("data", [])
            if isinstance(resp, dict)
            else (resp if isinstance(resp, list) else [])
        )
        mtf_items = [p for p in items if p.get("prod", "").upper() == "MTF"]
        r.delete(REDIS_MTF_POSITIONS)
        if mtf_items:
            pipe = r.pipeline()
            for p in mtf_items:
                symbol = p.get("trdSym", "").replace("-EQ", "").strip()
                if not symbol:
                    continue
                cf_qty = float(p.get("cfBuyQty", 0) or 0)
                cf_amt = float(p.get("cfBuyAmt", 0) or 0)
                avg_price = (cf_amt / cf_qty) if cf_qty > 0 else 0
                pipe.hset(
                    REDIS_MTF_POSITIONS,
                    symbol,
                    json.dumps(
                        {
                            "symbol": symbol,
                            "quantity": int(cf_qty),
                            "average_price": round(avg_price, 2),
                            "last_price": float(p.get("ltP", 0) or 0),
                            "pnl": float(p.get("unrealizedMTOM", 0) or 0),
                            "instrument_token": int(p.get("tok", 0) or 0),
                            "synced_at": datetime.now(INDIA_TZ).isoformat(),
                        }
                    ),
                )
            pipe.execute()
        r.set(REDIS_MTF_LAST_SYNC, datetime.now(INDIA_TZ).isoformat())
        print(f"[SYNC MTF] {len(mtf_items)} positions")
        return True
    except Exception as e:
        print(f"[SYNC MTF ERROR] {e}")
        return False


def sync_fo_positions(r):
    try:
        client = _create_kotak_client()
        resp = client.positions()
        items = []
        if isinstance(resp, dict):
            raw = resp.get("data", [])
            if isinstance(raw, list):
                items = raw
        elif isinstance(resp, list):
            items = resp

        fo_items = [
            p
            for p in items
            if p.get("exSeg", "").lower() in ("nse_fo", "bse_fo", "cde_fo", "mcx_fo")
            or p.get("exchange", "").lower() in ("nse_fo", "bse_fo", "cde_fo", "mcx_fo")
        ]

        r.delete(REDIS_FO_POSITIONS)
        if fo_items:
            pipe = r.pipeline()
            for p in fo_items:
                sym = p.get("trdSym", "").strip()
                if not sym:
                    continue
                pipe.hset(
                    REDIS_FO_POSITIONS,
                    sym,
                    json.dumps(
                        {
                            "symbol": sym,
                            "qty": int(p.get("flBuyQty", 0) or 0),
                            "avg_price": float(p.get("buyAmt", 0) or 0),
                            "ltp": float(p.get("ltP", 0) or 0),
                            "pnl": float(p.get("unrealizedMTOM", 0) or 0),
                            "product": p.get("prod", ""),
                            "segment": p.get("exSeg", ""),
                            "synced_at": datetime.now(INDIA_TZ).isoformat(),
                        }
                    ),
                )
            pipe.execute()

        r.set(REDIS_FO_LAST_SYNC, datetime.now(INDIA_TZ).isoformat())
        print(f"[SYNC FO] {len(fo_items)} positions")
        return True
    except Exception as e:
        print(f"[SYNC FO ERROR] {e}")
        return False


def background_sync(r):
    while True:
        time.sleep(SYNC_INTERVAL)
        sync_cnc(r)
        sync_mtf(r)
        sync_fo_positions(r)
