"""Testy jednostkowe generowania i weryfikacji tokenow JWT (auth.py).

Token jest jedynym dowodem tozsamosci w tym API — kazda sciezka odrzucenia
musi byc sprawdzona.
"""

import time

import jwt
import pytest

import auth

pytestmark = pytest.mark.unit


def _decode(token, key=None):
    return jwt.decode(token, key or auth.SECRET_KEY, algorithms=["HS256"])


# ---------------------------------------------------------------
# Poprawne tokeny
# ---------------------------------------------------------------

def test_token_zawiera_identyfikator_uzytkownika():
    """RFC 7519 wymaga, by 'sub' bylo tekstem — PyJWT to egzekwuje."""
    assert _decode(auth.generate_token(42))["sub"] == "42"


def test_token_ma_date_wystawienia_i_wygasniecia():
    payload = _decode(auth.generate_token(1))
    assert payload["exp"] > payload["iat"]


def test_token_wygasa_po_osmiu_godzinach():
    payload = _decode(auth.generate_token(1))
    assert payload["exp"] - payload["iat"] == 8 * 3600


def test_tokeny_roznych_uzytkownikow_sa_rozne():
    assert auth.generate_token(1) != auth.generate_token(2)


# ---------------------------------------------------------------
# Odrzucanie tokenow niepoprawnych
# ---------------------------------------------------------------

def test_token_podpisany_innym_kluczem_jest_odrzucany():
    # Klucz o pelnej dlugosci — testujemy odrzucenie obcego podpisu,
    # a nie ostrzezenie o zbyt krotkim kluczu.
    obcy = jwt.encode(
        {"sub": "1", "exp": int(time.time()) + 3600},
        "inny-klucz-o-dlugosci-co-najmniej-32-bajtow",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        _decode(obcy)


def test_token_z_naruszonym_podpisem_jest_odrzucany():
    token = auth.generate_token(1)
    naruszony = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(jwt.InvalidTokenError):
        _decode(naruszony)


def test_token_wygasly_jest_odrzucany():
    wygasly = jwt.encode(
        {"sub": 1, "iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600},
        auth.SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        _decode(wygasly)


def test_ciag_niebedacy_tokenem_jest_odrzucany():
    with pytest.raises(jwt.InvalidTokenError):
        _decode("to-nie-jest-token")


def test_algorytm_none_jest_odrzucany():
    """Klasyczny atak: token bez podpisu z naglowkiem alg=none."""
    niepodpisany = jwt.encode({"sub": 1}, key="", algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        _decode(niepodpisany)


# ---------------------------------------------------------------
# Konfiguracja klucza podpisujacego
# ---------------------------------------------------------------

def test_brak_secret_key_ostrzega_i_nie_przechodzi_bezszelestnie():
    """Uruchomienie bez SECRET_KEY musi glosno ostrzegac.

    Test w podprocesie — SECRET_KEY jest czytany w momencie importu modulu,
    a przeladowanie go w tym samym procesie zmienialoby klucz pozostalym testom.
    """
    import os
    import subprocess
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    env["PYTHONPATH"] = root

    wynik = subprocess.run(
        [sys.executable, "-W", "always", "-c", "import auth; print(auth.SECRET_KEY)"],
        capture_output=True, text=True, cwd=root, env=env,
    )

    assert wynik.returncode == 0
    assert "dev-only-insecure-key" in wynik.stdout
    assert "SECRET_KEY" in wynik.stderr, "Brak ostrzezenia o niebezpiecznym kluczu domyslnym"
