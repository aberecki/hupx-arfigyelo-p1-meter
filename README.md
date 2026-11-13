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

Indítás után nyisd meg a Macen a http://127.0.0.1:8765 címet. Az oldalon
megadhatod az ár felső határát (€/MWh) és a visszatáplálás alsó határát (W);
mindkét feltételnek teljesülnie kell, az egyenlő érték nem riaszt. A mentés
a következő mérésnél érvényes, újraindítás után is megmarad. Az oldal csak a
figyelő futása alatt érhető el, és nem indítja el önmagától a programot.

Alapértelmezésben a riasztás feltétele a `200 €/MWh` alatti ár és a
`0 W` feletti visszatáplálás. Amíg nincs mentett beállítás, az
`MAX_PRICE_EUR_MWH` és az `EXPORT_MIN_W` környezeti változóval is megadhatók.
A felületen mentett beállítások elsőbbséget élveznek, és a
`~/.config/hupx-arfigyelo-p1-meter/settings.json` fájlban tárolódnak.
Az értesítésekhez Gmail-feladó, alkalmazásjelszó és címzett szükséges;
Pushover-beállítás nem szükséges.
Egyszeri tesztküldéshez a program a mérő helyett `0 kW` exportot használ, és
csak akkor küld értesítést, ha az aktuális lekért ár a beállított árküszöb alatt van:

```bash
python p1_monitor.py --test-once
```

Jelszavakat/tokeneket ne commitolj; használj környezeti változókat vagy GitHub Secrets-et.
