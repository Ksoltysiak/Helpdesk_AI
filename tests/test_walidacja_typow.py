"""Testy odpornosci na nieprawidlowe TYPY danych wejsciowych.

Klient moze przyslac dowolny JSON. Wczesniej liczba lub obiekt w polu
tekstowym powodowaly nieobsluzony wyjatek (`len()` na int, blad wiazania
parametru SQLite) i odpowiedz HTTP 500 ze strona HTML — zamiast bledu 400
w formacie JSON, ktory obiecuje specyfikacja API.
"""

import pytest

pytestmark = pytest.mark.integration

# Wartosci, ktore nie sa tekstem, a klient moze je przyslac.
NIE_TEKST = [12345, 3.14, True, None, ["a", "b"], {"$ne": None}, {"a": 1}]


@pytest.mark.parametrize("wartosc", NIE_TEKST)
def test_nietekstowy_tytul_daje_400_a_nie_500(client, pracownik, wartosc):
    resp = client.post("/api/tickets", headers=pracownik,
                       json={"title": wartosc, "description": "poprawny opis"})
    assert resp.status_code == 400
    assert resp.is_json


@pytest.mark.parametrize("wartosc", NIE_TEKST)
def test_nietekstowy_opis_daje_400_a_nie_500(client, pracownik, wartosc):
    resp = client.post("/api/tickets", headers=pracownik,
                       json={"title": "poprawny tytul", "description": wartosc})
    assert resp.status_code == 400
    assert resp.is_json


@pytest.mark.parametrize("wartosc", NIE_TEKST)
def test_nietekstowa_notatka_daje_400_a_nie_500(client, technik, wartosc):
    resp = client.post("/api/tickets/1/notes", headers=technik, json={"content": wartosc})
    assert resp.status_code == 400
    assert resp.is_json


@pytest.mark.parametrize("wartosc", NIE_TEKST)
def test_nietekstowe_dane_dla_modulu_ai_daja_400(client, pracownik, wartosc):
    resp = client.post("/api/ai/categorize", headers=pracownik, json={"title": wartosc})
    assert resp.status_code == 400
    assert resp.is_json


def test_zadne_pole_tekstowe_nie_powoduje_bledu_serwera(client, pracownik, technik):
    """Zbiorczy przebieg — zaden wariant nie moze skonczyc sie kodem 5xx."""
    kody = []
    for wartosc in NIE_TEKST:
        kody.append(client.post("/api/tickets", headers=pracownik,
                                json={"title": wartosc, "description": wartosc}).status_code)
        kody.append(client.post("/api/tickets/1/notes", headers=technik,
                                json={"content": wartosc}).status_code)
    assert all(k < 500 for k in kody), f"Wystapil blad serwera: {kody}"


# ---------------------------------------------------------------
# Puste i bialoznakowe wartosci
# ---------------------------------------------------------------

@pytest.mark.parametrize("wartosc", ["", "   ", "\t", "\n  \n"])
def test_tytul_z_samych_bialych_znakow_jest_odrzucany(client, pracownik, wartosc):
    resp = client.post("/api/tickets", headers=pracownik,
                       json={"title": wartosc, "description": "opis"})
    assert resp.status_code == 400


def test_wartosci_sa_przycinane_z_bialych_znakow(client, pracownik):
    tid = client.post("/api/tickets", headers=pracownik,
                      json={"title": "  Tytul z odstepami  ",
                            "description": "  opis  "}).get_json()["id"]
    dane = client.get(f"/api/tickets/{tid}", headers=pracownik).get_json()
    assert dane["title"] == "Tytul z odstepami"
    assert dane["description"] == "opis"


def test_dlugosc_liczona_po_przycieciu(client, pracownik):
    """Same odstepy nie moga sztucznie przekraczac limitu."""
    resp = client.post("/api/tickets", headers=pracownik,
                       json={"title": " " * 100 + "x" * 200 + " " * 100,
                             "description": "opis"})
    assert resp.status_code == 201


# ---------------------------------------------------------------
# Bledy zawsze w formacie JSON
# ---------------------------------------------------------------

def test_niedozwolona_metoda_zwraca_json(client, technik):
    """DELETE nie jest obslugiwane — odpowiedz musi byc JSON-em, nie HTML-em."""
    resp = client.delete("/api/tickets/1", headers=technik)
    assert resp.status_code == 405
    assert resp.is_json
    assert "error" in resp.get_json()


def test_uszkodzony_json_nie_powoduje_bledu_serwera(client, pracownik):
    resp = client.post("/api/tickets", headers=pracownik,
                       data="{to nie jest json", content_type="application/json")
    assert resp.status_code == 400
    assert resp.is_json


def test_brak_tresci_zadania_nie_powoduje_bledu_serwera(client, pracownik):
    assert client.post("/api/tickets", headers=pracownik).status_code == 400


def test_bardzo_duze_zadanie_jest_odrzucane(client, pracownik):
    """Ladunek znacznie powyzej limitu musi zostac odrzucony, nie przetworzony."""
    resp = client.post("/api/tickets", headers=pracownik,
                       json={"title": "x" * 100_000, "description": "y" * 100_000})
    assert resp.status_code == 400


def test_token_z_nieliczbowym_identyfikatorem_jest_odrzucany(client):
    """Poprawnie podpisany token, ale 'sub' nie jest liczba — brak tozsamosci."""
    import time
    import jwt
    from app import config as auth

    podrobiony = jwt.encode(
        {"sub": "nie-liczba", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        auth.SECRET_KEY, algorithm="HS256",
    )
    resp = client.get("/api/tickets", headers={"Authorization": f"Bearer {podrobiony}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------
# Nieoczekiwany blad serwera nie ujawnia szczegolow
# ---------------------------------------------------------------

@pytest.fixture
def app_z_bledna_trasa(app):
    """Aplikacja z trasa, ktora celowo rzuca wyjatek."""
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/api/_awaria")
    def awaria():
        raise RuntimeError("tajny szczegol implementacji: haslo do bazy = 12345")

    @app.route("/_awaria_frontend")
    def awaria_frontend():
        raise RuntimeError("tajny szczegol implementacji")

    return app


def test_blad_serwera_w_api_zwraca_json_bez_szczegolow(app_z_bledna_trasa):
    resp = app_z_bledna_trasa.test_client().get("/api/_awaria")
    assert resp.status_code == 500
    assert resp.is_json
    tresc = resp.get_data(as_text=True)
    assert "tajny szczegol" not in tresc
    assert "RuntimeError" not in tresc
    assert "Traceback" not in tresc


def test_blad_serwera_poza_api_tez_nie_ujawnia_szczegolow(app_z_bledna_trasa):
    resp = app_z_bledna_trasa.test_client().get("/_awaria_frontend")
    assert resp.status_code == 500
    assert "tajny szczegol" not in resp.get_data(as_text=True)


def test_blad_404_poza_api_nie_jest_zamieniany_na_json(client):
    """Sciezki frontendu maja dalej dostawac aplikacje, nie blad API."""
    resp = client.get("/dowolna/podstrona")
    assert resp.status_code == 200
    assert b"<!DOCTYPE html>" in resp.data


def test_niedozwolona_metoda_poza_api_nie_zwraca_json(client):
    """Handler ma dotyczyc wylacznie /api/* — reszta zachowuje zachowanie Flaska."""
    resp = client.post("/")
    assert resp.status_code == 405
    assert not resp.is_json
