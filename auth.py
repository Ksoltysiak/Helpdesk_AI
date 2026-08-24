import os
import time
import warnings
import jwt
from functools import wraps
from flask import request, jsonify, g
from db import get_db

_MIN_KEY_BYTES = 32  # RFC 7518 sekcja 3.2 dla HMAC-SHA256

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = "dev-only-insecure-key"
    warnings.warn(
        "SECRET_KEY env var not set — using insecure default. "
        "Set SECRET_KEY in production.",
        stacklevel=1,
    )
elif len(SECRET_KEY.encode()) < _MIN_KEY_BYTES:
    # Krotki klucz HMAC obniza realna sile podpisu tokenow.
    warnings.warn(
        f"SECRET_KEY is shorter than {_MIN_KEY_BYTES} bytes — weak signing key. "
        f"Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"",
        stacklevel=1,
    )

_TOKEN_TTL = 8 * 3600  # 8 hours


def generate_token(user_id: int) -> str:
    now = int(time.time())
    # RFC 7519 wymaga, aby "sub" bylo lancuchem znakow — PyJWT od wersji 2.12
    # odrzuca tokeny z wartoscia liczbowa.
    payload = {"sub": str(user_id), "iat": now, "exp": now + _TOKEN_TTL}
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
    try:
        uid = int(uid)
    except (TypeError, ValueError):
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
