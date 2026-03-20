# test_bitget_native.py
import time
import json
import hmac
import base64
import hashlib
import requests

API_KEY = "bg_b2d405188981b90b1003f7127981ca53"
API_SECRET = "a56a94b4c02ecdc7aa0755a644f8926d2409d94bdccf33428ff1b8f42ff2de97"
API_PASSPHRASE = "X6I2e0QALXAd"

BASE_URL = "https://api.bitget.com"

SYMBOL = "XAUUSDT"
PRODUCT_TYPE = "usdt-futures"
MARGIN_MODE = "isolated"
MARGIN_COIN = "USDT"
SIZE = "0.01"


# =========================
# 署名（ここが超重要）
# =========================
def sign(timestamp, method, request_path, body=""):
    message = f"{timestamp}{method.upper()}{request_path}{body}"
    digest = hmac.new(
        API_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()


def get_headers(method, request_path, body=""):
    timestamp = str(int(time.time() * 1000))
    return {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": sign(timestamp, method, request_path, body),
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-PASSPHRASE": API_PASSPHRASE,
        "Content-Type": "application/json",
        "locale": "en-US",
        "PAPTRADING": "1",  # ← デモ必須
    }


# =========================
# 残高取得（40009確認）
# =========================
def get_balance():
    path = "/api/v2/mix/account/accounts"
    query = f"?productType={PRODUCT_TYPE}&marginCoin={MARGIN_COIN}"
    url = BASE_URL + path + query

    headers = get_headers("GET", path + query)

    r = requests.get(url, headers=headers)
    print("\n[BALANCE]")
    print(r.status_code, r.text)


# =========================
# 注文（one-way専用）
# =========================
def place_order(side):
    path = "/api/v2/mix/order/place-order"
    url = BASE_URL + path

    payload = {
        "symbol": SYMBOL,
        "productType": PRODUCT_TYPE,
        "marginMode": MARGIN_MODE,
        "marginCoin": MARGIN_COIN,
        "size": SIZE,
        "side": side,
        "orderType": "market",
        "clientOid": f"demo-{int(time.time()*1000)}",
    }

    body = json.dumps(payload, separators=(",", ":"))
    headers = get_headers("POST", path, body)

    r = requests.post(url, headers=headers, data=body)

    print(f"\n[ORDER {side.upper()}]")
    print(r.status_code, r.text)


# =========================
# 実行
# =========================
if __name__ == "__main__":
    print("=== BITGET DEMO TEST ===")

    # ① 残高（ここで40009消えるか確認）
    get_balance()

    # ② 買い
    place_order("buy")

    time.sleep(2)

    # ③ 売り（one-wayではそのまま反対売買）
    place_order("sell")