# HUPX árfigyelő + P1 meter

- `main.py` + GitHub Actions: másnapi alacsony ár riasztás, `prices.json` frissítés (változatlan).
- `p1_monitor.py`: valós idejű figyelő, e-mail/Pushover riasztás, ha az aktuális tőzsdei ár negatív **és** a P1 mérő visszatáplálást mér.

A P1 mérő helyi hálózaton van, ezért a `p1_monitor.py`-t otthoni gépen futtasd:

```bash
pip install -r requirements.txt
export ENTSOE_KEY=... EMAIL_SENDER=... EMAIL_PASSWORD=... EMAIL_TARGET=...
export P1_METER_URL=http://adaone.local/json
# opcionális: P1_EXPORT_PATH, P1_IMPORT_PATH, P1_SCALE_TO_W, EXPORT_MIN_W, POLL_SECONDS, COOLDOWN_SECONDS
python p1_monitor.py
```

Jelszavakat/tokeneket ne commitolj; használj környezeti változókat vagy GitHub Secrets-et.
