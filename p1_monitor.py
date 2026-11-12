"""Figyelő: küszöb alatti másnapi piaci ár + P1 visszatáplálás -> riasztás.

A P1 mérő (GreenHess ADA) csak a helyi hálózaton érhető el, ezért ezt a
szkriptet otthoni gépen/Raspberry Pi-n kell futtatni (nem GitHub Actionsben).
"""
import os
import time
import argparse
import math
import requests
import pandas as pd
from entsoe import EntsoePandasClient
from main import send_alert, clean_secret

P1_URL = clean_secret(os.environ.get('P1_METER_URL')) or 'http://adaone.local/json'
# Pontozott JSON-útvonal a visszatáplálás és vételezés mezőjéhez
EXPORT_PATH = os.environ.get('P1_EXPORT_PATH', 'instantaneous_power_export')
IMPORT_PATH = os.environ.get('P1_IMPORT_PATH', 'instantaneous_power_import')
# Az ADA One kW-ban adja az értékeket, amelyeket W-ra váltunk.
P1_SCALE = float(os.environ.get('P1_SCALE_TO_W', '1000'))
EXPORT_MIN_W = float(os.environ.get('EXPORT_MIN_W', '0'))
MAX_PRICE_EUR_MWH = float(os.environ.get('MAX_PRICE_EUR_MWH', '200'))
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
    try:
        export_w = float(dig(data, EXPORT_PATH)) * P1_SCALE
        import_w = float(dig(data, IMPORT_PATH)) * P1_SCALE
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError("A P1 válaszból nem olvasható ki az import- és exportteljesítmény.") from None
    if not all(math.isfinite(value) and value >= 0 for value in (export_w, import_w)):
        raise ValueError("A P1 import- és exportteljesítményének érvényes, nem negatív számnak kell lennie.")
    return export_w, import_w


_cache = {'slot': None, 'prices': None}


def current_price_eur_kwh(now=None):
    """A magyar idő szerinti aktuális negyedóra HU day-ahead ára."""
    def clock():
        return now if now is not None else pd.Timestamp.now(tz='Europe/Budapest')

    while True:
        current = clock().tz_convert('Europe/Budapest')
        day = current.normalize()
        slot = current.tz_convert('UTC').floor('15min').tz_convert('Europe/Budapest')
        if _cache['slot'] != slot:
            client = EntsoePandasClient(api_key=API_KEY)
            prices = client.query_day_ahead_prices(
                'HU', start=day, end=day + pd.DateOffset(days=1))
            if clock().tz_convert('UTC').floor('15min') != slot.tz_convert('UTC'):
                continue
            _cache.update(slot=slot, prices=prices)
        prices = _cache['prices']
        if not isinstance(prices.index, pd.DatetimeIndex) or prices.index.tz is None:
            _cache.update(slot=None, prices=None)
            raise ValueError("Az ENTSO-E árakhoz időzónás időbélyegek szükségesek.")
        values = prices[prices.index == slot]
        if len(values) != 1 or not math.isfinite(values.iloc[0]):
            _cache.update(slot=None, prices=None)
            raise ValueError(f"Nincs egyértelmű ár az aktuális negyedórára: {slot.isoformat()}")
        return values.iloc[0] / 1000


def main(test_once=False):
    last_alert = 0
    while True:
        try:
            export_w, import_w = (0, 0) if test_once else read_p1()
            price = current_price_eur_kwh()
            print(f"ár={price * 1000:.2f} €/MWh, export={export_w:.0f} W, import={import_w:.0f} W")
            price_matches = price * 1000 < MAX_PRICE_EUR_MWH
            export_matches = test_once or export_w > EXPORT_MIN_W
            if price_matches and export_matches and (test_once or time.time() - last_alert > COOLDOWN_SECONDS):
                send_alert(
                    "Figyelem! Visszatáplálás alacsony tőzsdei ár mellett",
                    "Figyelem! Jelenleg ilyen tőzsdei ár mellett ennyit táplál ki "
                    "napelemes rendszere a hálózatra. A veszteségek elkerülése "
                    "érdekében szüntesse meg a visszatáplálást!\n\n"
                    f"Tőzsdei ár: {price * 1000:.2f} €/MWh\n"
                    f"Visszatáplálás: {export_w / 1000:.3f} kW")
                last_alert = time.time()
                print("E-mail elküldve.")
            elif test_once:
                print(f"A teszt nem küldött riasztást: az ár nem kisebb mint {MAX_PRICE_EUR_MWH:.2f} €/MWh.")
        except Exception as e:
            print(f"Hiba: {e}")
            if test_once:
                raise
        if test_once:
            return
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test-once",
        action="store_true",
        help="Egyszeri teszt 0 kW exportértékkel; a mérő lekérdezése nélkül.",
    )
    main(test_once=parser.parse_args().test_once)
