"""Rozszerzenia Flaska tworzone raz i podpinane w fabryce aplikacji."""

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app import config

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=config.RATELIMIT_STORAGE_URI,
)


def klucz_logowania():
    """Klucz limitu dla logowania: adres IP + nazwa uzytkownika.

    Sam limit na adres IP nie chroni przed rozproszona proba odgadniecia hasla
    do jednego konta (kazde zadanie z innego adresu ma wlasna pule). Dolozenie
    nazwy uzytkownika ogranicza liczbe prob per konto, niezaleznie od zrodla.

    Swiadomie NIE stosujemy blokady konta po N probach: napastnik moglby wtedy
    celowo zablokowac dostep prawdziwym uzytkownikom. Spowolnienie daje ochrone
    przed zgadywaniem hasla, nie dajac narzedzia do odcinania ludzi od systemu.
    """
    dane = request.get_json(silent=True) or {}
    login = dane.get("username")
    if not isinstance(login, str):
        login = ""
    return f"{get_remote_address()}|{login.lower()[:64]}"
