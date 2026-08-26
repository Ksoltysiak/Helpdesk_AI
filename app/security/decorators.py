"""Dekoratory kontroli dostępu.

Autoryzacja jest sprawdzana **po stronie serwera przy każdym żądaniu** —
interfejs nie decyduje o uprawnieniach, jedynie odzwierciedla to, na co
serwer pozwala.
"""

from functools import wraps

from flask import request, jsonify, g

from app.data import users
from app.security.tokens import token_z_zadania, id_uzytkownika_z_tokenu


def current_user():
    """Użytkownik przypisany do tokenu z żądania albo None."""
    uid = id_uzytkownika_z_tokenu(token_z_zadania(request.headers.get("Authorization", "")))
    if uid is None:
        return None
    # Token może być poprawnie podpisany, a użytkownik już usunięty.
    return users.po_id(uid)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "Wymagana autoryzacja"}), 401
        g.user = user
        return f(*args, **kwargs)
    return wrapper


def roles_required(*role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"error": "Wymagana autoryzacja"}), 401
            if user["role"] not in role:
                return jsonify({"error": "Brak uprawnien dla tej operacji"}), 403
            g.user = user
            return f(*args, **kwargs)
        return wrapper
    return decorator
