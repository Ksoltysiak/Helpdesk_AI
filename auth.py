from functools import wraps
from flask import request, jsonify, g
from db import get_db


def current_user():
    uid = request.headers.get("X-User-Id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "Wymagana autoryzacja (naglowek X-User-Id)"}), 401
        g.user = user
        return f(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"error": "Wymagana autoryzacja (naglowek X-User-Id)"}), 401
            if user["role"] not in roles:
                return jsonify({"error": "Brak uprawnien dla tej operacji"}), 403
            g.user = user
            return f(*args, **kwargs)
        return wrapper
    return decorator
