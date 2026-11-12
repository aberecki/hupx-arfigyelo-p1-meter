"""Valós idejű figyelő: negatív tőzsdei ár + P1 visszatáplálás -> riasztás.

A P1 mérő (GreenHess ADA) csak a helyi hálózaton érhető el, ezért ezt a
szkriptet otthoni gépen/Raspberry Pi-n kell futtatni (nem GitHub Actionsben).
"""
import os
import time
import requests
import pandas as pd
from entsoe import EntsoePandasClient
from main import send_alert, clean_secret

P1_URL = clean_secret(os.environ.get('P1_METER_URL')) or 'http://adaone.local/json'
# Pontozott JSON-útvonal a visszatáplálás (W) és vételezés (W) mezőjéhez
EXPORT_PATH = os.environ.get('P1_EXPORT_PATH', 'active_power_export')
IMPORT_PATH = os.environ.get('P1_IMPORT_PATH', 'active_power_import')
# Ha a mérő kW-ban adja az értéket, állítsd 1000-re
P1_SCALE = float(os.environ.get('P1_SCALE_TO_W', '1'))
EXPORT_MIN_W = float(os.environ.get('EXPORT_MIN_W', '100'))
POLL_SECONDS = int(os.environ.get('POLL_SECONDS', '60'))
COOLDOWN_SECONDS = int(os.environ.get('COOLDOWN_SECONDS', '3600'))
API_KEY = clean_secret(os.environ.get('ENTSOE_KEY'))


def dig(data, path):
    for key in path.split('.'):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def read_p1():
    r = requests.get(P1_URL, timeout=10)
    r.raise_for_status()
    data = r.json()
    export_w = float(dig(data, EXPORT_PATH)) * P1_SCALE
    import_w = float(dig(data, IMPORT_PATH)) * P1_SCALE
    return export_w, import_w


_cache = {'day': None, 'prices': None}


def current_price_eur_kwh():
    """Az aktuális negyedórás HU day-ahead ár (EUR/kWh), napi cache-sel."""
    now = pd.Timestamp.now(tz='Europe/Budapest')
    day = now.normalize()
    if _cache['day'] != day:
        client = EntsoePandasClient(api_key=API_KEY)
        _cache['prices'] = client.query_day_ahead_prices(
            'HU', start=day, end=day + pd.Timedelta(days=1))
        _cache['day'] = day
    prices = _cache['prices']
    return prices[prices.index <= now].iloc[-1] / 1000


def main():
    last_alert = 0
    while True:
        try:
            price = current_price_eur_kwh()
            export_w, import_w = read_p1()
            print(f"ár={price:.4f} €/kWh, export={export_w:.0f} W, import={import_w:.0f} W")
            if price < 0 and export_w >= EXPORT_MIN_W and time.time() - last_alert > COOLDOWN_SECONDS:
                send_alert(
                    "⚡ Negatív ár + visszatáplálás",
                    f"A tőzsdei ár most {price:.4f} €/kWh (negatív), "
                    f"közben {export_w:.0f} W-ot táplálsz vissza a hálózatba.\n"
                    f"Növeld az önfogyasztást vagy korlátozd a termelést!")
                last_alert = time.time()
        except Exception as e:
            print(f"Hiba: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
