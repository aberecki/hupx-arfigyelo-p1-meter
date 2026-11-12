import os
import json
import smtplib
import traceback
import pandas as pd
from email.message import EmailMessage
from entsoe import EntsoePandasClient

# --- 1. BEÁLLÍTÁSOK ---
def clean_secret(value):
    if not value: return ""
    return value.strip().replace('\xa0', '')

API_KEY = clean_secret(os.environ.get('ENTSOE_KEY'))
EMAIL_SENDER = clean_secret(os.environ.get('EMAIL_SENDER'))
EMAIL_PASSWORD = clean_secret(os.environ.get('EMAIL_PASSWORD'))
EMAIL_TARGET = clean_secret(os.environ.get('EMAIL_TARGET'))

# Határérték: 0.1 EUR/kWh (100 EUR/MWh)
PRICE_LIMIT = 100.0 

def format_intervals(cheap_data):
    if cheap_data.empty: return ""
    intervals = []
    start_time = cheap_data.index[0]
    for i in range(1, len(cheap_data)):
        diff = cheap_data.index[i] - cheap_data.index[i-1]
        if diff > pd.Timedelta(minutes=15):
            end_time = cheap_data.index[i-1] + pd.Timedelta(minutes=15)
            intervals.append(f"• {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")
            start_time = cheap_data.index[i]
    end_time = cheap_data.index[-1] + pd.Timedelta(minutes=15)
    intervals.append(f"• {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")
    return "\n".join(intervals)

def send_alert(subject, body):
    if not (EMAIL_SENDER and EMAIL_PASSWORD and EMAIL_TARGET):
        raise RuntimeError("E-mail nincs konfigurálva")
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_TARGET
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise RuntimeError(f"E-mail küldési hiba: {e}") from e

def check_prices():
    print(f"--- INDÍTÁS: HMKE TERMELÉSI ABLAK MONITORING (08-18h) ---")
    if not API_KEY: return
    try:
        client = EntsoePandasClient(api_key=API_KEY)
        now = pd.Timestamp.now(tz='Europe/Budapest')
        target_day = (now + pd.Timedelta(days=1)).normalize()
        
        prices = client.query_day_ahead_prices('HU', start=target_day, end=target_day + pd.Timedelta(days=1))
        if prices.empty: return

        target_prices = prices[prices.index.normalize() == target_day]
        
        # 1. JSON MENTÉS (A weboldal továbbra is mindent mutat)
        data_list = [{"time": t.isoformat(), "price_kwh": round(p/1000, 4)} for t, p in target_prices.items()]
        with open('prices.json', 'w') as f:
            json.dump({"day": str(target_day.date()), "data": data_list}, f)

        # 2. SZŰRÉS A TERMELÉSI ABLAKRA (08:00 - 18:00)
        # Csak azokat az órákat tartjuk meg az értesítéshez, amik 8 és 18 közé esnek
        production_window = target_prices[
            (target_prices.index.hour >= 8) & (target_prices.index.hour < 18)
        ]

        # Alacsony ár figyelése CSAK a termelési ablakban
        cheap_intervals = production_window[production_window < PRICE_LIMIT]
        
        if not cheap_intervals.empty:
            time_list = format_intervals(cheap_intervals)
            min_price = cheap_intervals.min() / 1000
            
            subject = f"⚠️ HMKE RIASZTÁS: {target_day.date()}"
            
            body = (
                f"Kedves Termelő!\n\n"
                f"Holnap a termelési időszakban 08:00-18:00 között várhatóan az átvételi ár {min_price:.4f} €/kWh alá esik. "
                f"Érdemes maximalizálni az önfogyasztást!\n\n"
                f"JAVASOLT AKTÍV IDŐSZAKOK (TERMELÉS ALATT):\n{time_list}\n\n"
                f"JAVASLATOK:\n"
                f"🚗 Töltsd az autót!\n"
                f"🧺 Nagyfogyasztók (mosás, szárítás) időzítése!\n"
                f"🌡️ Hűtés/fűtés indítása a termelési csúcsban!\n\n"
                f"Átvételi árak: https://aberecki.github.io/hupx-arfigyelo-p1-meter/"
            )
            
            send_alert(subject, body)
            print(f"📧 Értesítés elküldve a termelési ablakra szűrve.")
        else:
            print("Holnap a termelési ablakban nincs kritikus ár.")
            
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    check_prices()
