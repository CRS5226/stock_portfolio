import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

INDIA_TZ = ZoneInfo("Asia/Kolkata")
OTP_EXPIRY_SEC = 120
SYNC_INTERVAL = 180

CONFIG_FILES_MTF_MIS = ["config_mtf1500.json", "config_fo.json"]
CONFIG_NSE = "config_kotak_nse.json"
CONFIG_BSE = "config_kotak_bse.json"
CONFIG_FO_FILE = "config_fo.json"
CONFIG_FO_BSE_FILE = "config_fo_bse.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN_400a")
CHAT_IDS_FILE = "telegram_chat_ids_30a.json"

INDEX_CODES = {
    "NIFTY 50",
    "NIFTY BANK",
    "NIFTY FIN SERVICE",
    "NIFTY NEXT 50",
    "NIFTY MID SELECT",
    "SENSEX",
}

INDEX_MAP = {
    "NIFTY 50": "NIFTY",
    "NIFTY BANK": "BANKNIFTY",
    "NIFTY FIN SERVICE": "FINNIFTY",
    "NIFTY NEXT 50": "NIFTYNXT50",
    "NIFTY MID SELECT": "MIDCPNIFTY",
}
INDEX_SYMBOLS = set(INDEX_MAP.keys())

KOTAK_CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
KOTAK_MOBILE = os.getenv("KOTAK_MOBILE")
KOTAK_MPIN = os.getenv("KOTAK_MPIN")
KOTAK_UCC = os.getenv("KOTAK_UCC")
KOTAK_TOTP_SECRET = os.getenv("KOTAK_TOTP_SECRET")

REDIS_CNC_HOLDINGS = "KOTAK:CNC:HOLDINGS"
REDIS_CNC_LAST_SYNC = "KOTAK:CNC:LAST_SYNC"
REDIS_MTF_POSITIONS = "KOTAK:MTF:POSITIONS"
REDIS_MTF_LAST_SYNC = "KOTAK:MTF:LAST_SYNC"
REDIS_OTP_PENDING = "KOTAK:OTP_PENDING"
REDIS_CNC_ORDER_PFX = "KOTAK:CNC:ORDER:"
REDIS_MTF_ORDER_PFX = "KOTAK:MTF:ORDER:"
REDIS_MIS_ORDER_PFX = "KOTAK:MIS:ORDER:"
REDIS_CO_ORDER_PFX = "KOTAK:CO:ORDER:"
REDIS_BO_ORDER_PFX = "KOTAK:BO:ORDER:"
REDIS_PREFIX_5M = "ETF_5M"
REDIS_PREFIX_1D = "ETF_1D"

REDIS_FO_POSITIONS = "KOTAK:FO:POSITIONS"
REDIS_FO_LAST_SYNC = "KOTAK:FO:LAST_SYNC"
REDIS_FO_OTP = "KOTAK:FO:OTP_PENDING"
REDIS_FO_ORDER_PFX = "KOTAK:FO:ORDER:"

CURRENCY_SYMBOLS = {
    "USDINR": "USD / INR",
    "EURINR": "EUR / INR",
    "GBPINR": "GBP / INR",
    "JPYINR": "JPY / INR",
    "EURUSD": "EUR / USD",
    "GBPUSD": "GBP / USD",
    "USDJPY": "USD / JPY",
}

COMMODITY_SYMBOLS = {
    "GOLD": "Gold (1 kg)",
    "GOLDM": "Gold Mini (100 g)",
    "SILVER": "Silver (30 kg)",
    "SILVERM": "Silver Mini (5 kg)",
    "SILVERMIC": "Silver Micro (1 kg)",
    "CRUDEOIL": "Crude Oil (100 bbl)",
    "CRUDEOILM": "Crude Oil Mini (10 bbl)",
    "NATURALGAS": "Natural Gas (1250 mmBtu)",
    "COPPER": "Copper (1 MT)",
    "ZINC": "Zinc (1 MT)",
    "LEAD": "Lead (1 MT)",
    "NICKEL": "Nickel (250 kg)",
    "ALUMINIUM": "Aluminium (1 MT)",
}
