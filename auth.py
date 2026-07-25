import os
import time
import warnings
import jwt
from functools import wraps
from flask import request, jsonify, g
from db import get_db

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = "dev-only-insecure-key"
    warnings.warn(
        "SECRET_KEY env var not set — using insecure default. "
        "Set SECRET_KEY in production.",
        stacklevel=1,
    )

_TOKEN_TTL = 8 * 3600  # 8 hours


def generate_token(user_id: int) -> str:
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + _TOKEN_TTL}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _token_from_request():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def current_user():
    token = _token_from_request()
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    uid = payload.get("sub")
    if uid is None:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "Wymagana autoryzacja"}), 401
        g.user = user
        return f(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"error": "Wymagana autoryzacja"}), 401
            if user["role"] not in roles:
                return jsonify({"error": "Brak uprawnien dla tej operacji"}), 403
            g.user = user
            return f(*args, **kwargs)
        return wrapper
    return decorator
