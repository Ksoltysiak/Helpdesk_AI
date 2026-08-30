"""Punkty końcowe uwierzytelniania."""

from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash

from app.data import users
from app.extensions import limiter, klucz_logowania
from app.security.decorators import login_required
from app.security.tokens import generate_token

bp = Blueprint("auth", __name__)


@bp.route("/auth/login", methods=["POST"])
@limiter.limit("10 per minute; 30 per hour")                            # na adres IP
@limiter.limit("5 per minute; 20 per hour", key_func=klucz_logowania)   # na konto
def login():
    dane = request.get_json(silent=True) or {}
    username = dane.get("username", "")
    password = dane.get("password", "")

    # Odpowiedź jest celowo identyczna dla złego hasła, nieznanego loginu
    # i nieprawidłowego typu — komunikat nie zdradza, które konta istnieją.
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "Nieprawidlowy login lub haslo"}), 401

    user = users.po_nazwie_z_hasłem(username)
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Nieprawidlowy login lub haslo"}), 401

    return jsonify({
        "id":    user["id"],
        "name":  user["name"],
        "role":  user["role"],
        "token": generate_token(user["id"]),
    })


@bp.route("/auth/me", methods=["GET"])
@login_required
def me():
    """Odtworzenie sesji na podstawie zapisanego tokenu (np. po odświeżeniu strony).

    Interfejs weryfikuje token tutaj, zamiast ufać danym zapisanym
    w przeglądarce.
    """
    return jsonify({"id": g.user["id"], "name": g.user["name"], "role": g.user["role"]})
