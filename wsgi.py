"""Punkt wejścia dla serwera WSGI (gunicorn) oraz uruchomienia lokalnego.

    gunicorn --bind 0.0.0.0:5000 wsgi:app
    python wsgi.py
"""

import os

from app import create_app, config
from app.data.database import init_db

app = create_app()

if __name__ == "__main__":
    if not os.path.exists(config.DB_PATH):
        init_db()
    app.run(port=5000, debug=False)
