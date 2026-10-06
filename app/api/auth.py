"""Punkty końcowe uwierzytelniania."""

from functools import cache

from flask import Blueprint, jsonify, g
from werkzeug.security import check_password_hash, generate_password_hash

from app.api.validation import obiekt_json
from app.data import users
from app.extensions import limiter, klucz_logowania
from app.security.decorators import login_required
from app.security.tokens import generate_token

bp = Blueprint("auth", __name__)


@cache
def _hash_zastepczy():
    """Hash sprawdzany, gdy konto nie istnieje.

    Weryfikacja hasła jest celowo kosztowna (dziesiątki milisekund). Gdyby
    przy nieznanym loginie ją pomijać, odpowiedź przychodziłaby wyraźnie
    szybciej — a czas odpowiedzi zdradzałby, które konta istnieją, mimo
    identycznego komunikatu. Liczony raz na proces, przy pierwszym użyciu.
    """
    return generate_password_hash("konto-nie-istnieje")


def _tozsamosc(user):
    """Dane, które interfejs pokazuje o zalogowanej osobie.

    Klient (firma) jest pusty dla personelu helpdesku — technik i administrator
    obsługują wszystkie firmy.
    """
    return {
        "id":          user["id"],
        "name":        user["name"],
        "role":        user["role"],
        "client_id":   user["client_id"],
        "client_name": user["client_name"],
    }


@bp.route("/auth/login", methods=["POST"])
@limiter.limit("10 per minute; 30 per hour")                            # na adres IP
@limiter.limit("5 per minute; 20 per hour", key_func=klucz_logowania)   # na konto
def login():
    dane = obiekt_json()
    username = dane.get("username", "")
    password = dane.get("password", "")

    # Odpowiedź jest celowo identyczna dla złego hasła, nieznanego loginu
    # i nieprawidłowego typu — komunikat nie zdradza, które konta istnieją.
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "Nieprawidlowy login lub haslo"}), 401

    user = users.po_nazwie_z_hasłem(username)
    hash_hasla = user["password"] if user else _hash_zastepczy()
    if not check_password_hash(hash_hasla, password) or not user:
        return jsonify({"error": "Nieprawidlowy login lub haslo"}), 401

    return jsonify({**_tozsamosc(user), "token": generate_token(user["id"])})


@bp.route("/auth/me", methods=["GET"])
@login_required
def me():
    """Odtworzenie sesji na podstawie zapisanego tokenu (np. po odświeżeniu strony).

    Interfejs weryfikuje token tutaj, zamiast ufać danym zapisanym
    w przeglądarce.
    """
    return jsonify(_tozsamosc(g.user))
