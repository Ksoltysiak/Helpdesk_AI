"""Testy integracyjne uwierzytelniania — pelny stos Flask + baza danych."""

import pytest

from conftest import auth_header

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------
# Logowanie
# ---------------------------------------------------------------

def test_poprawne_logowanie_zwraca_token_i_role(client):
    resp = client.post("/api/auth/login", json={"username": "k.nowak", "password": "haslo123"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["role"] == "pracownik"
    assert data["name"] == "Katarzyna Nowak"
    assert data["token"]


def test_odpowiedz_logowania_nie_ujawnia_hasla(client):
    """Ani hasla, ani jego skrotu nie moze byc w odpowiedzi."""
    resp = client.post("/api/auth/login", json={"username": "k.nowak", "password": "haslo123"})
    tresc = resp.get_data(as_text=True).lower()
    assert "haslo123" not in tresc
    assert "scrypt" not in tresc and "pbkdf2" not in tresc


def test_haslo_jest_hashowane_w_bazie(app):
    """Baza nie moze przechowywac hasla otwartym tekstem."""
    from app import config as db_module
    import sqlite3

    conn = sqlite3.connect(db_module.DB_PATH)
    zapisane = conn.execute(
        "SELECT password FROM users WHERE username = 'k.nowak'"
    ).fetchone()[0]
    conn.close()

    assert zapisane != "haslo123"
    assert zapisane.startswith("scrypt:") or zapisane.startswith("pbkdf2:")


@pytest.mark.parametrize("dane", [
    {"username": "k.nowak", "password": "zle-haslo"},
    {"username": "nie-istnieje", "password": "haslo123"},
    {"username": "k.nowak"},
    {"password": "haslo123"},
    {},
])
def test_bledne_dane_logowania_daja_401(client, dane):
    assert client.post("/api/auth/login", json=dane).status_code == 401


def test_komunikat_bledu_nie_zdradza_czy_login_istnieje(client):
    """Ta sama tresc bledu dla zlego hasla i nieznanego uzytkownika."""
    zle_haslo = client.post("/api/auth/login", json={"username": "k.nowak", "password": "x"})
    zly_login = client.post("/api/auth/login", json={"username": "nikt", "password": "x"})
    assert zle_haslo.get_json() == zly_login.get_json()


def test_typ_inny_niz_tekst_nie_powoduje_bledu_serwera(client):
    """Proba pomylenia typow (np. {"$ne": ...}) musi konczyc sie 401, nie 500."""
    resp = client.post("/api/auth/login", json={"username": {"a": 1}, "password": ["b"]})
    assert resp.status_code == 401


# ---------------------------------------------------------------
# Odtwarzanie sesji (/auth/me)
# ---------------------------------------------------------------

def test_auth_me_zwraca_dane_zalogowanego(client, pracownik):
    resp = client.get("/api/auth/me", headers=pracownik)
    assert resp.status_code == 200
    assert resp.get_json() == {"id": 1, "name": "Katarzyna Nowak", "role": "pracownik"}


def test_auth_me_nie_zwraca_hasla(client, technik):
    assert "password" not in client.get("/api/auth/me", headers=technik).get_json()


# ---------------------------------------------------------------
# Ochrona endpointow
# ---------------------------------------------------------------

@pytest.mark.parametrize("sciezka", [
    "/api/auth/me",
    "/api/dashboard",
    "/api/tickets",
    "/api/tickets/1",
])
def test_brak_tokenu_daje_401(client, sciezka):
    assert client.get(sciezka).status_code == 401


@pytest.mark.parametrize("naglowek", [
    {"Authorization": "Bearer nieprawidlowy.token.jwt"},
    {"Authorization": "Bearer "},
    {"Authorization": "niepoprawny-schemat"},
    {"Authorization": "Basic a2Vjczpwc3M="},
    {"X-User-Id": "1"},  # stary, podatny mechanizm — nie moze juz dzialac
])
def test_niepoprawny_naglowek_autoryzacji_daje_401(client, naglowek):
    assert client.get("/api/tickets", headers=naglowek).status_code == 401


def test_token_dla_usunietego_uzytkownika_jest_odrzucany(client, app):
    """Token moze byc poprawnie podpisany, ale uzytkownik juz nie istnieje."""
    from app.security.tokens import generate_token

    resp = client.get("/api/tickets", headers=auth_header(generate_token(9999)))
    assert resp.status_code == 401


def test_wygasly_token_jest_odrzucany_przez_api(client):
    """Sciezka wygasniecia musi konczyc sie 401, a nie bledem serwera."""
    import time
    import jwt
    from app import config as auth

    wygasly = jwt.encode(
        {"sub": 1, "iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600},
        auth.SECRET_KEY, algorithm="HS256",
    )
    assert client.get("/api/tickets", headers=auth_header(wygasly)).status_code == 401


def test_token_bez_identyfikatora_uzytkownika_jest_odrzucany(client):
    """Poprawnie podpisany token, ale bez pola 'sub' — brak tozsamosci."""
    import time
    import jwt
    from app import config as auth

    bez_sub = jwt.encode(
        {"iat": int(time.time()), "exp": int(time.time()) + 3600},
        auth.SECRET_KEY, algorithm="HS256",
    )
    assert client.get("/api/tickets", headers=auth_header(bez_sub)).status_code == 401


@pytest.mark.parametrize("metoda,sciezka,dane", [
    ("post",  "/api/tickets",         {"title": "T", "description": "O"}),
    ("patch", "/api/tickets/1",       {"status": "W trakcie"}),
    ("post",  "/api/tickets/1/notes", {"content": "N"}),
    ("get",   "/api/tickets/1/audit", None),
])
def test_endpointy_wymagajace_roli_odrzucaja_brak_tokenu(client, metoda, sciezka, dane):
    """Kontrola roli nie moze byc jedyna bramka — brak tokenu tez daje 401."""
    wywolanie = getattr(client, metoda)
    resp = wywolanie(sciezka, json=dane) if dane else wywolanie(sciezka)
    assert resp.status_code == 401
