import requests


BINANCE_BTCUSDT_PRICE_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"


def get_btc_price():
    try:
        response = requests.get(BINANCE_BTCUSDT_PRICE_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        return float(data["price"])
    except Exception:
        return None
