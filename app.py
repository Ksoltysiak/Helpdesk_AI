from flask import Flask, jsonify
import os
from db import close_db, init_db, DB_PATH
from routes import api


def create_app():
    app = Flask(__name__)
    app.register_blueprint(api, url_prefix="/api")
    app.teardown_appcontext(close_db)

    @app.after_request
    def cors(response):
        # Integracja z frontendem: zezwala aplikacji frontendowej dzialajacej
        # na innym porcie/domenie na wywolywanie tego API z poziomu przegladarki.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-User-Id"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
        return response

    @app.route("/")
    def index():
        return jsonify({
            "api": "Inteligentny HelpDesk IT",
            "status": "dziala",
            "info": "Punkty koncowe dostepne pod /api/...",
        })

    return app


app = create_app()

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(port=5000, debug=True)
