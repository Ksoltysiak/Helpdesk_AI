"""Fabryka aplikacji — spina warstwy i konfiguruje zachowanie HTTP.

Podział na warstwy:

    app/api/       — warstwa HTTP: trasy, walidacja żądań, kody odpowiedzi
    app/domain/    — reguły biznesowe: kategoryzacja, cykl życia zgłoszenia
    app/data/      — dostęp do bazy: schemat, zapytania, migracje
    app/security/  — tokeny i kontrola dostępu
    app/config.py  — cała konfiguracja środowiskowa w jednym miejscu

Zależności biegną w jedną stronę: `api` korzysta z `domain` i `data`,
`domain` nie wie nic o HTTP ani o bazie.
"""

import gzip
import os

from flask import Flask, send_from_directory, jsonify, request, redirect
from flask_swagger_ui import get_swaggerui_blueprint
from werkzeug.middleware.proxy_fix import ProxyFix

from app import config
from app.api import auth, errors, meta, tickets
from app.data.database import close_db
from app.extensions import limiter


def create_app():
    app = Flask(__name__)

    # Za odwrotnym proxy prawdziwy adres klienta jest w X-Forwarded-For.
    # Bez tego wszystkie żądania wyglądają jakby szły z jednego IP i dzieliłyby
    # jeden licznik limitu logowania — jeden atakujący zablokowałby wszystkich.
    #
    # Włączane WYŁĄCZNIE jawnie: gdyby aplikacja stała bezpośrednio w sieci,
    # zaufanie do tego nagłówka pozwoliłoby go podrobić i obejść limit.
    if config.TRUST_PROXY:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.teardown_appcontext(close_db)
    limiter.init_app(app)

    for modul in (auth.bp, tickets.bp, meta.bp):
        app.register_blueprint(modul, url_prefix="/api")

    errors.zarejestruj(app)
    _dokumentacja(app)
    _zachowanie_http(app)
    _frontend(app)

    return app


def _dokumentacja(app):
    """Specyfikacja OpenAPI i interaktywna dokumentacja.

    Pliki Swagger UI są dołączone do paczki (bez CDN) — działają offline
    i nie wymagają luźniejszej polityki CSP.
    """
    app.register_blueprint(
        get_swaggerui_blueprint(config.DOCS_URL, config.SPEC_URL,
                                config={"app_name": "HelpDesk IT — API"}),
        url_prefix=config.DOCS_URL,
    )

    @app.route(config.SPEC_URL)
    def openapi_spec():
        return send_from_directory(config.BASE_DIR, config.SPEC_FILE,
                                   mimetype="application/yaml")


def _zachowanie_http(app):
    """Przekierowanie na HTTPS, nagłówki bezpieczeństwa, kompresja i cache."""

    @app.before_request
    def przekieruj_na_https():
        if config.FORCE_HTTPS and not request.is_secure:
            return redirect(request.url.replace("http://", "https://", 1), code=308)

    @app.after_request
    def kompresuj(response):
        """Kompresja gzip dla odpowiedzi tekstowych.

        Odpowiedzi JSON i pliki frontendu składają się z powtarzalnego tekstu
        i kompresują się bardzo dobrze — to największy pojedynczy zysk dla
        użytkowników na wolnym łączu.
        """
        if (
            response.direct_passthrough
            or not 200 <= response.status_code < 300
            or "Content-Encoding" in response.headers
            or response.content_length is None
            or response.content_length < config.MIN_BAJTOW_DO_KOMPRESJI
            or "gzip" not in request.headers.get("Accept-Encoding", "")
        ):
            return response

        if (response.content_type or "").split(";")[0] not in config.TYPY_KOMPRESOWANE:
            return response

        dane = gzip.compress(response.get_data(), compresslevel=6)
        response.set_data(dane)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(dane))
        response.headers.add("Vary", "Accept-Encoding")
        return response

    @app.after_request
    def naglowki_bezpieczenstwa(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Aplikacja nie korzysta z tych funkcji — jawne wyłączenie ogranicza
        # szkody, gdyby doszło do wstrzyknięcia obcego skryptu.
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )
        # Skrypty wyłącznie z własnego serwera — aplikacja nie ładuje żadnej
        # biblioteki JavaScript z sieci CDN.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'"
        )
        # HSTS ma sens wyłącznie po HTTPS — wysłany po HTTP jest ignorowany,
        # a przy lokalnym uruchomieniu potrafiłby zablokować dostęp do localhost.
        if config.FORCE_HTTPS:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.after_request
    def naglowki_cache(response):
        """Dane zgłoszeń nie mogą być cache'owane, pliki statyczne powinny."""
        if request.path.startswith("/api/"):
            # Odpowiedź API zapisana w cache przeglądarki mogłaby zostać
            # pokazana innemu użytkownikowi tego samego urządzenia.
            response.headers["Cache-Control"] = "no-store"
        elif request.path.rsplit(".", 1)[-1] in ("css", "js", "svg", "png", "ico", "woff2"):
            # "no-cache" nie znaczy "nie buforuj" — znaczy "buforuj, ale za
            # każdym razem potwierdź aktualność". Nazwy plików nie zawierają
            # skrótu treści, więc max-age zostawiałby po wdrożeniu stary kod
            # frontendu wykonywany wobec nowego API.
            response.headers["Cache-Control"] = "no-cache"
        return response


def _frontend(app):
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        # Nieznane ścieżki /api/... nie mogą trafiać do frontendu — klient API
        # musi dostać błędny status w JSON, a nie stronę HTML z kodem 200.
        if path.startswith("api/"):
            return jsonify({"error": "Nie znaleziono punktu koncowego"}), 404
        if path and os.path.exists(os.path.join(config.FRONTEND_DIR, path)):
            return send_from_directory(config.FRONTEND_DIR, path)
        return send_from_directory(config.FRONTEND_DIR, "index.html")
