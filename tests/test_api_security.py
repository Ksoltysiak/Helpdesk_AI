"""Testy integracyjne zabezpieczen warstwy HTTP: naglowki, obsluga
nieznanych sciezek, ograniczanie liczby zadan i serwowanie frontendu.
"""

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------
# Naglowki bezpieczenstwa
# ---------------------------------------------------------------

@pytest.mark.parametrize("naglowek,wartosc", [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
])
def test_naglowki_bezpieczenstwa_sa_ustawione(client, naglowek, wartosc):
    assert client.get("/").headers.get(naglowek) == wartosc


def test_polityka_csp_jest_obecna_i_domyslnie_restrykcyjna(client):
    csp = client.get("/").headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp


def test_naglowki_obowiazuja_takze_dla_api(client, technik):
    assert client.get("/api/tickets", headers=technik).headers.get("X-Frame-Options") == "DENY"


def test_brak_wildcard_cors(client):
    """Frontend jest serwowany z tego samego zrodla — CORS jest zbedny."""
    assert "Access-Control-Allow-Origin" not in client.get("/api/tickets").headers


# ---------------------------------------------------------------
# REGRESJA: nieznane sciezki /api/* zwracaly strone HTML z kodem 200
#
# Trasa serwujaca frontend przechwytywala kazda nieznana sciezke, wiec
# literowka w adresie API konczyla sie odpowiedzia 200 z dokumentem HTML —
# klient API nie mial jak odroznic jej od poprawnej odpowiedzi.
# ---------------------------------------------------------------

@pytest.mark.parametrize("sciezka", [
    "/api/nieistniejacy",
    "/api/tickets/None",
    "/api/tickets/abc",
    "/api/auth/nieznane",
])
def test_nieznany_endpoint_api_zwraca_json_404(client, sciezka):
    resp = client.get(sciezka)
    assert resp.status_code == 404
    assert resp.is_json
    assert "error" in resp.get_json()


def test_nieznany_endpoint_api_nie_zwraca_html(client):
    assert b"<!DOCTYPE html>" not in client.get("/api/nieistniejacy").data


# ---------------------------------------------------------------
# Serwowanie frontendu (nie moze ucierpiec na powyzszej poprawce)
# ---------------------------------------------------------------

def test_strona_glowna_zwraca_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<!DOCTYPE html>" in resp.data


def test_pliki_statyczne_sa_serwowane(client):
    assert client.get("/style.css").status_code == 200
    assert client.get("/script.js").status_code == 200


def test_nieznana_sciezka_poza_api_zwraca_aplikacje(client):
    """Trasy frontendu obsluguje JavaScript — serwer oddaje index.html."""
    resp = client.get("/dowolna/podstrona")
    assert resp.status_code == 200
    assert b"<!DOCTYPE html>" in resp.data


# ---------------------------------------------------------------
# Ograniczanie liczby prob logowania
# ---------------------------------------------------------------

def test_powtarzane_proby_logowania_sa_blokowane(rate_limited_client):
    """Po przekroczeniu limitu logowanie musi zwrocic 429, nie 401."""
    kody = [
        rate_limited_client.post(
            "/api/auth/login", json={"username": "k.nowak", "password": "zle"}
        ).status_code
        for _ in range(15)
    ]
    assert 429 in kody, "Brak blokady — atak slownikowy nie jest ograniczany"
    assert kody.index(429) >= 10, "Limit zadzialal zbyt wczesnie"


def test_limit_nie_dotyczy_zwyklych_odczytow(rate_limited_client, technik):
    kody = [
        rate_limited_client.get("/api/tickets", headers=technik).status_code
        for _ in range(15)
    ]
    assert kody.count(200) == 15
