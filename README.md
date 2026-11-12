# HUPX árfigyelő + P1 meter

- `main.py` + GitHub Actions: másnapi alacsony ár riasztás, `prices.json` frissítés (változatlan).
- `p1_monitor.py`: e-mail riasztás, ha az aktuális másnapi piaci ár a beállított küszöb alatt van **és** a P1 mérő visszatáplálást mér.

A figyelő az ENTSO-E magyar zónára közzétett day-ahead árát használja: mindig
a mai nap, magyar idő szerinti aktuális negyedórájához tartozó árat keresi.
Ez nem valós idejű (intraday) tőzsdei ár. A lekérdezést minden negyedórában
frissíti; hiányzó ár esetén hibát jelez, nem használ korábbi negyedórás árat.

A P1 mérő helyi hálózaton van, ezért a `p1_monitor.py`-t otthoni gépen futtasd:

```bash
pip install -r requirements.txt
export ENTSOE_KEY=... EMAIL_SENDER=... EMAIL_PASSWORD=... EMAIL_TARGET=...
export P1_METER_URL=http://adaone.local/json
# opcionális: P1_EXPORT_PATH, P1_IMPORT_PATH, P1_SCALE_TO_W, EXPORT_MIN_W, MAX_PRICE_EUR_MWH, POLL_SECONDS, COOLDOWN_SECONDS
python p1_monitor.py
```

Az ADA One alapértelmezett JSON-mezői az `instantaneous_power_export` és
`instantaneous_power_import`, kW-ban; a program ezeket W-ra váltja.
Más JSON-szerkezet vagy mértékegység esetén a mezőútvonalak és a
`P1_SCALE_TO_W` beállíthatók. A mérő JSON-válasza jelszót és tokent is
tartalmazhat, ezért a teljes választ ne oszd meg.

Alapértelmezésben a riasztás feltétele a `200 €/MWh` alatti ár és a
`0 W` feletti visszatáplálás. A küszöbök környezeti változóval módosíthatók.
Az értesítésekhez Gmail-feladó, alkalmazásjelszó és címzett szükséges;
Pushover-beállítás nem szükséges.
Egyszeri tesztküldéshez a program a mérő helyett `0 kW` exportot használ, és
csak akkor küld értesítést, ha az aktuális lekért ár 200 €/MWh alatt van:

```bash
python p1_monitor.py --test-once
```

Jelszavakat/tokeneket ne commitolj; használj környezeti változókat vagy GitHub Secrets-et.
