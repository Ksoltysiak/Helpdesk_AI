from flask import Flask, send_from_directory
import os
from db import close_db, init_db, DB_PATH
from routes import api

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


def create_app():
    app = Flask(__name__)
    app.register_blueprint(api, url_prefix="/api")
    app.teardown_appcontext(close_db)

    @app.after_request
    def cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-User-Id"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
        return response

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
            return send_from_directory(FRONTEND_DIR, path)
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(port=5000, debug=True)
