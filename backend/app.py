from flask import Flask, send_from_directory, jsonify
from flask_swagger_ui import get_swaggerui_blueprint
import os
from db import close_db, init_db, DB_PATH
from routes import api
from rate_limit import limiter

BASE_DIR     = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

DOCS_URL = "/api/docs"
SPEC_URL = "/api/openapi.yaml"


def create_app():
    app = Flask(__name__)
    app.register_blueprint(api, url_prefix="/api")
    app.teardown_appcontext(close_db)
    limiter.init_app(app)

    @app.route("/health")
    def health():
        return {"status": "ok"}

    # Interaktywna dokumentacja API. Pliki Swagger UI sa dolaczone do paczki
    # (bez CDN) — dzialaja offline i nie wymagaja luzniejszej polityki CSP.
    app.register_blueprint(
        get_swaggerui_blueprint(DOCS_URL, SPEC_URL, config={"app_name": "HelpDesk IT — API"}),
        url_prefix=DOCS_URL,
    )

    @app.route(SPEC_URL)
    def openapi_spec():
        return send_from_directory(os.path.join(BASE_DIR, ".."), "openapi.yaml", mimetype="application/yaml")

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"]        = "DENY"
        response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://unpkg.com 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
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
