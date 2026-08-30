"""Wystawianie i weryfikacja tokenów JWT."""

import time
from datetime import timedelta

import jwt

from app import config

# Tolerancja na rozjazd zegarow miedzy wystawieniem a weryfikacja tokenu.
#
# Token niesie czas wystawienia (`iat`) i wygasniecia (`exp`). Gdy zegar
# weryfikujacego jest choc o sekunde do tylu wzgledem wystawiajacego, PyJWT
# odrzuca token jako "jeszcze niewazny" — a uzytkownik dostaje 401 mimo
# poprawnego logowania. Przy kilku procesach czy maszynach drobny rozjazd
# jest normalny.
#
# Kilka sekund luzu to standardowa praktyka i nie oslabia zabezpieczenia
# w istotny sposob: token wygasly nadal zostaje odrzucony, tylko o te kilka
# sekund pozniej.
LUZ_ZEGARA = timedelta(seconds=10)


def generate_token(user_id: int) -> str:
    now = int(time.time())
    # RFC 7519 wymaga, aby "sub" bylo lancuchem znakow — PyJWT od wersji 2.12
    # odrzuca tokeny z wartoscia liczbowa.
    payload = {"sub": str(user_id), "iat": now, "exp": now + config.TOKEN_TTL}
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


def token_z_zadania(naglowek: str):
    """Wyciąga token z nagłówka `Authorization: Bearer <token>`."""
    if naglowek and naglowek.startswith("Bearer "):
        return naglowek[7:]
    return None


def id_uzytkownika_z_tokenu(token: str):
    """Identyfikator z poprawnego tokenu albo None.

    Każda przyczyna odrzucenia — brak tokenu, wygaśnięcie, zły podpis,
    nieliczbowy identyfikator — kończy się tak samo: brakiem tożsamości.
    Klient nie dowiaduje się, na czym dokładnie polegał problem.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"],
                             leeway=LUZ_ZEGARA)
    except jwt.InvalidTokenError:      # obejmuje ExpiredSignatureError
        return None

    uid = payload.get("sub")
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None
