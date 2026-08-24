"""Testy integracyjne zabezpieczen warstwy HTTP: naglowki, obsluga
nieznanych sciezek, ograniczanie liczby zadan i serwowanie frontendu.
"""

import re

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


@pytest.mark.parametrize("dyrektywa", [
    "object-src 'none'",       # blokuje wtyczki i osadzone obiekty
    "base-uri 'self'",         # uniemozliwia przekierowanie sciezek wzglednych
    "frame-ancestors 'none'",  # clickjacking, takze dla przegladarek bez X-Frame-Options
    "form-action 'self'",      # formularz nie wysle danych na obcy serwer
])
def test_csp_zawiera_dyrektywy_ograniczajace(client, dyrektywa):
    assert dyrektywa in client.get("/").headers.get("Content-Security-Policy", "")


def test_csp_nie_zezwala_na_skrypty_z_cdn(client):
    """Skrypty tylko z wlasnego serwera — zaden obcy host nie jest dozwolony."""
    csp = client.get("/").headers.get("Content-Security-Policy", "")
    script_src = [c for c in csp.split(";") if c.strip().startswith("script-src")][0]
    for host in ("unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "*"):
        assert host not in script_src


def test_frontend_nie_laduje_skryptow_z_obcych_serwerow(client):
    """Obcy skrypt wykonuje sie z pelnymi uprawnieniami strony — takze
    z dostepem do tokenu w sessionStorage. Zaden nie moze wrocic niepostrzezenie."""
    strona = client.get("/").get_data(as_text=True)
    skrypty = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', strona)
    zewnetrzne = [s for s in skrypty if s.startswith(("http://", "https://", "//"))]
    assert not zewnetrzne, f"Frontend laduje obce skrypty: {zewnetrzne}"


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
    """Po przekroczeniu limitu logowanie musi zwrocic 429, nie 401.

    Obowiazuja dwa limity naraz: 10/min na adres IP oraz ostrzejszy 5/min
    na konkretne konto. Przy powtarzaniu tego samego loginu pierwszy zadziala
    limit na konto.
    """
    kody = [
        rate_limited_client.post(
            "/api/auth/login", json={"username": "k.nowak", "password": "zle"}
        ).status_code
        for _ in range(15)
    ]
    assert 429 in kody, "Brak blokady — atak slownikowy nie jest ograniczany"
    assert kody.index(429) >= 5, "Limit zadzialal zbyt wczesnie"
    assert kody[0] == 401, "Pierwsza proba musi byc normalnie obsluzona"


def test_limit_na_konto_nie_blokuje_innych_uzytkownikow(rate_limited_client):
    """Zablokowanie jednego konta nie moze odciac pozostalych.

    Dlatego zamiast blokady konta stosowane jest spowolnienie z kluczem
    zawierajacym nazwe uzytkownika — napastnik nie zablokuje cudzego dostepu.
    """
    for _ in range(8):
        rate_limited_client.post("/api/auth/login",
                                 json={"username": "k.nowak", "password": "zle"})

    inny = rate_limited_client.post(
        "/api/auth/login", json={"username": "m.lewandowski", "password": "tech123"}
    )
    assert inny.status_code == 200, "Limit dla jednego konta odcial inne konto"


def test_limit_nie_dotyczy_zwyklych_odczytow(rate_limited_client, technik):
    kody = [
        rate_limited_client.get("/api/tickets", headers=technik).status_code
        for _ in range(15)
    ]
    assert kody.count(200) == 15
