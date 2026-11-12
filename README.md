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

Az árküszöb alapértelmezésben `500 €/MWh`; a normál exportküszöb `100 W`.
Egyszeri tesztküldéshez a program a mérő helyett `0 kW` exportot használ, és
csak akkor küld értesítést, ha az aktuális lekért ár 500 €/MWh alatt van:

```bash
python p1_monitor.py --test-once
```

Jelszavakat/tokeneket ne commitolj; használj környezeti változókat vagy GitHub Secrets-et.
