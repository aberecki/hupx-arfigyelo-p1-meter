"""Local-only settings for the P1 monitor."""
import html
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


SETTINGS_PATH = Path.home() / '.config' / 'hupx-arfigyelo-p1-meter' / 'settings.json'


def validate_settings(price, export):
    try:
        price, export = float(price), float(export)
    except (TypeError, ValueError):
        raise ValueError('Mindkét küszöbnek számnak kell lennie.') from None
    if not math.isfinite(price) or not math.isfinite(export) or export < 0:
        raise ValueError('Az ár véges szám, a visszatáplálás véges, nem negatív szám legyen.')
    return {'price_eur_mwh': price, 'export_w': export}


def load_settings(defaults):
    try:
        with SETTINGS_PATH.open(encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        return validate_settings(defaults['price_eur_mwh'], defaults['export_w'])
    except (OSError, ValueError) as error:
        raise ValueError(f'A beállítások nem olvashatók: {error}') from error
    try:
        return validate_settings(data['price_eur_mwh'], data['export_w'])
    except (KeyError, TypeError) as error:
        raise ValueError('A beállítások fájlja hiányos vagy hibás.') from error


def save_settings(settings):
    SETTINGS_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=SETTINGS_PATH.parent, prefix='.settings-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(settings, file, allow_nan=False)
            file.write('\n')
        os.replace(temp_path, SETTINGS_PATH)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


class SettingsServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, defaults):
        super().__init__(address, SettingsHandler)
        self.defaults = defaults
        self.token = secrets.token_urlsafe(32)
        self.origin = f'http://127.0.0.1:{self.server_port}'


class SettingsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def respond(self, status, body):
        encoded = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(encoded)

    def valid_host(self):
        return self.headers.get('Host') == self.server.origin.removeprefix('http://')

    def page(self, message='', status=200):
        try:
            settings = load_settings(self.server.defaults)
        except ValueError as error:
            self.respond(500, html.escape(str(error)))
            return
        price = html.escape(str(settings['price_eur_mwh']), quote=True)
        export = html.escape(str(settings['export_w']), quote=True)
        notice = html.escape(message)
        self.respond(status, f'''<!doctype html>
<html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Árfigyelő beállításai</title><style>
body{{font:16px system-ui,sans-serif;background:#f3f6fa;color:#17233b;margin:0;padding:24px}}
main{{max-width:560px;margin:5vh auto;background:white;padding:28px;border-radius:16px;box-shadow:0 6px 24px #17233b18}}
h1{{font-size:1.55rem}} p{{line-height:1.5}} label{{display:block;font-weight:600;margin-top:22px}}
input{{box-sizing:border-box;width:100%;padding:12px;margin-top:8px;font:inherit;border:1px solid #9aa8bb;border-radius:8px}}
button{{margin-top:24px;background:#1a5bba;color:white;border:0;border-radius:8px;padding:12px 20px;font:inherit;cursor:pointer}}
.notice{{color:#165b32;font-weight:600}} .hint{{color:#485872;font-size:.9rem}}
</style></head><body><main><h1>E-mail értesítés beállításai</h1>
<p>Értesítést akkor küldünk, ha <strong>mindkét</strong> feltétel teljesül.</p>
<p class="notice" role="status">{notice}</p>
<form method="post" action="/save">
<input type="hidden" name="token" value="{self.server.token}">
<label for="price">Tőzsdei ár ez alatt (€/MWh)</label>
<input id="price" name="price" type="number" step="any" value="{price}" required>
<label for="export">Visszatáplálás e felett (W)</label>
<input id="export" name="export" type="number" min="0" step="any" value="{export}" required>
<button type="submit">Beállítások mentése</button></form>
<p class="hint">A módosítás a következő mérésnél érvényes. Sikeres e-mail után egy óráig nincs új értesítés.
Az ár az aktuális negyedóra ENTSO-E day-ahead ára. Az oldal csak ezen a gépen érhető el.</p>
</main></body></html>''')

    def do_GET(self):
        if not self.valid_host():
            self.respond(403, 'Érvénytelen cím.')
        elif urlsplit(self.path).path != '/':
            self.respond(404, 'Az oldal nem található.')
        else:
            self.page()

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') != self.server.origin:
            self.respond(403, 'Érvénytelen kérés.')
            return
        if self.path != '/save':
            self.respond(404, 'Az oldal nem található.')
            return
        if self.headers.get_content_type() != 'application/x-www-form-urlencoded':
            self.respond(400, 'Érvénytelen űrlap.')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Érvénytelen űrlapméret.')
            form = parse_qs(self.rfile.read(length).decode('utf-8'), strict_parsing=True)
            if any(len(form.get(key, [])) != 1 for key in ('token', 'price', 'export')):
                raise ValueError('Hiányos űrlap.')
            if not secrets.compare_digest(form['token'][0], self.server.token):
                self.respond(403, 'Érvénytelen kérés.')
                return
            settings = validate_settings(form['price'][0], form['export'][0])
            save_settings(settings)
        except (ValueError, UnicodeError) as error:
            self.page(str(error), 400)
            return
        except OSError:
            self.page('Nem sikerült menteni a beállításokat.', 500)
            return
        self.page('A beállításokat elmentettük.')


def start_server(defaults, port=8765):
    server = SettingsServer(('127.0.0.1', port), defaults)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
