from flask import Flask, send_from_directory, jsonify, request, redirect
from flask_swagger_ui import get_swaggerui_blueprint
from werkzeug.middleware.proxy_fix import ProxyFix
import gzip
import os
from db import close_db, init_db, DB_PATH
from routes import api
from rate_limit import limiter

BASE_DIR     = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

DOCS_URL = "/api/docs"
SPEC_URL = "/api/openapi.yaml"

_MIN_BAJTOW_DO_KOMPRESJI = 1024   # ponizej tego narzut gzip przewaza nad zyskiem
_TYPY_KOMPRESOWANE = {
    "application/json", "application/yaml",
    "text/html", "text/css", "text/javascript", "application/javascript",
    "image/svg+xml",
}


def _wlaczone(nazwa):
    return os.environ.get(nazwa, "").lower() in ("1", "true", "yes", "on")


def create_app():
    app = Flask(__name__)
    app.register_blueprint(api, url_prefix="/api")
    app.teardown_appcontext(close_db)

    # Za odwrotnym proxy prawdziwy adres klienta jest w X-Forwarded-For.
    # Bez tego wszystkie zadania wygladaja jakby szly z jednego IP i dzielilyby
    # jeden licznik limitu logowania — jeden atakujacy zablokowalby wszystkich.
    #
    # Wlaczane WYLACZNIE jawnie: gdyby aplikacja stala bezposrednio w sieci,
    # zaufanie do tego naglowka pozwoliloby go podrobic i obejsc limit.
    if _wlaczone("TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    limiter.init_app(app)

    wymuszaj_https = _wlaczone("FORCE_HTTPS")

    @app.before_request
    def przekieruj_na_https():
        if wymuszaj_https and not request.is_secure:
            return redirect(request.url.replace("http://", "https://", 1), code=308)

    # Interaktywna dokumentacja API. Pliki Swagger UI sa dolaczone do paczki
    # (bez CDN) — dzialaja offline i nie wymagaja luzniejszej polityki CSP.
    app.register_blueprint(
        get_swaggerui_blueprint(DOCS_URL, SPEC_URL, config={"app_name": "HelpDesk IT — API"}),
        url_prefix=DOCS_URL,
    )

    @app.route(SPEC_URL)
    def openapi_spec():
        return send_from_directory(BASE_DIR, "openapi.yaml", mimetype="application/yaml")

    @app.after_request
    def kompresuj(response):
        """Kompresja gzip dla odpowiedzi tekstowych.

        Odpowiedzi JSON i pliki frontendu skladaja sie z powtarzalnego tekstu
        i kompresuja sie bardzo dobrze — to najwiekszy pojedynczy zysk dla
        uzytkownikow na wolnym laczu.
        """
        if (
            response.direct_passthrough
            or response.status_code < 200
            or response.status_code >= 300
            or "Content-Encoding" in response.headers
            or response.content_length is None
            or response.content_length < _MIN_BAJTOW_DO_KOMPRESJI
            or "gzip" not in request.headers.get("Accept-Encoding", "")
        ):
            return response

        typ = (response.content_type or "").split(";")[0]
        if typ not in _TYPY_KOMPRESOWANE:
            return response

        dane = gzip.compress(response.get_data(), compresslevel=6)
        response.set_data(dane)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(dane))
        response.headers.add("Vary", "Accept-Encoding")
        return response

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"]        = "DENY"
        response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
        # Aplikacja nie korzysta z tych funkcji — jawne wylaczenie ogranicza
        # szkody, gdyby doszlo do wstrzykniecia obcego skryptu.
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )
        # HSTS ma sens wylacznie po HTTPS — wyslany po HTTP jest ignorowany,
        # a przy lokalnym uruchomieniu potrafilby zablokowac dostep do localhost.
        if wymuszaj_https:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        # Skrypty wylacznie z wlasnego serwera — aplikacja nie laduje juz
        # zadnej biblioteki JavaScript z sieci CDN.
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
        return response

    # Klient API musi dostawac JSON takze przy bledach — domyslne strony HTML
    # Flaska lamalyby udokumentowany kontrakt (i myliy kod bledu z trescia).
    def blad_json(kod, komunikat):
        def handler(_e):
            if request.path.startswith("/api/"):
                return jsonify({"error": komunikat}), kod
            return _e
        return handler

    app.register_error_handler(404, blad_json(404, "Nie znaleziono punktu koncowego"))
    app.register_error_handler(405, blad_json(405, "Metoda niedozwolona dla tej sciezki"))
    app.register_error_handler(429, blad_json(429, "Zbyt wiele zadan — sprobuj ponownie pozniej"))

    @app.errorhandler(500)
    def blad_wewnetrzny(_e):
        # Tresc wyjatku nigdy nie trafia do klienta — moglaby zdradzic
        # szczegoly implementacji lub fragmenty danych.
        if request.path.startswith("/api/"):
            return jsonify({"error": "Blad wewnetrzny serwera"}), 500
        return "Blad wewnetrzny serwera", 500

    @app.after_request
    def naglowki_cache(response):
        """Dane zgloszen nie moga byc cache'owane, pliki statyczne powinny.

        Odpowiedz API zapisana w cache przegladarki mogłaby zostac pokazana
        innemu uzytkownikowi tej samej przegladarki po wylogowaniu.
        """
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.path.rsplit(".", 1)[-1] in ("css", "js", "svg", "png", "ico", "woff2"):
            # Pliki wersjonowane sa trescia — walidacja przez ETag Flaska.
            response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
        return response

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        # Nieznane sciezki /api/... nie moga trafiac do frontendu — klient API
        # musi dostac bledny status w JSON, a nie strone HTML z kodem 200.
        if path.startswith("api/"):
            return jsonify({"error": "Nie znaleziono punktu koncowego"}), 404
        if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
            return send_from_directory(FRONTEND_DIR, path)
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(port=5000, debug=False)
