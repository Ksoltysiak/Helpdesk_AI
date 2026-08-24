import os

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Domyslnie licznik trzymany jest w pamieci procesu. Przy uruchomieniu
# wieloprocesowym (gunicorn --workers N) kazdy proces ma wtedy wlasny licznik,
# wiec faktyczny limit jest N razy wyzszy niz zadeklarowany.
#
# Ustawienie RATELIMIT_STORAGE_URI (np. redis://host:6379) powoduje, ze
# wszystkie procesy dziela jeden licznik i limit dziala zgodnie z deklaracja.
STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=STORAGE_URI,
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
