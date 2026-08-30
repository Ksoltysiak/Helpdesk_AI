"""Testy zgodnosci specyfikacji OpenAPI z rzeczywista implementacja.

Dokumentacja pisana recznie rozjezdza sie z kodem — w tym projekcie zdarzylo
sie to juz raz (README opisywal naglowek X-User-Id dlugo po przejsciu na JWT).
Ponizsze testy sprawiaja, ze rozjazd konczy sie czerwonym testem, a nie cicho
mylaca dokumentacja.
"""

import os
import re

import pytest
import yaml

from app.domain.ai import CATEGORIES, SLA_HOURS
from app.domain.tickets import TRANSITIONS
from app import config as db_module
from app.data import database

pytestmark = pytest.mark.integration

SPEC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.yaml"
)

# Konwerter sciezki Flaska na notacje OpenAPI: <int:ticket_id> -> {ticket_id}
_PARAM = re.compile(r"<(?:[^:<>]+:)?([^<>]+)>")


@pytest.fixture(scope="module")
def spec():
    with open(SPEC_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# Trasy pod /api/, ktore NIE sa czescia API dla klientow — dokumentacja
# opisuje sama siebie i nie ma jej w specyfikacji.
_POZA_SPECYFIKACJA = ("/api/docs", "/api/openapi.yaml")


def _sciezki_flaska(app):
    """Sciezki i metody API, w notacji OpenAPI.

    Filtrujemy po SCIEZCE, a nie po nazwie blueprintu: warstwa HTTP jest
    podzielona na kilka blueprintow (auth, tickets, meta), a podzial moze sie
    jeszcze zmienic. Sciezka /api/ jest stabilnym kryterium.
    """
    znalezione = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        if rule.rule.startswith(_POZA_SPECYFIKACJA):
            continue
        sciezka = _PARAM.sub(r"{\1}", rule.rule)
        sciezka = sciezka[len("/api"):] or "/"
        metody = {m.lower() for m in rule.methods} - {"head", "options"}
        znalezione.setdefault(sciezka, set()).update(metody)
    return znalezione


def _sciezki_specyfikacji(spec):
    znalezione = {}
    for sciezka, operacje in spec["paths"].items():
        metody = {m for m in operacje if m in
                  {"get", "post", "put", "patch", "delete"}}
        znalezione[sciezka] = metody
    return znalezione


# ---------------------------------------------------------------
# Poprawnosc samej specyfikacji
# ---------------------------------------------------------------

def test_specyfikacja_jest_poprawnym_yaml(spec):
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"]
    assert spec["paths"]


def test_serwer_wskazuje_prefiks_api(spec):
    assert spec["servers"][0]["url"] == "/api"


def test_zdefiniowano_uwierzytelnianie_tokenem(spec):
    schemat = spec["components"]["securitySchemes"]["bearerAuth"]
    assert schemat["type"] == "http"
    assert schemat["scheme"] == "bearer"
    assert schemat["bearerFormat"] == "JWT"


def test_uwierzytelnianie_obowiazuje_domyslnie(spec):
    """Bezpieczna wartosc domyslna: chronione jest wszystko poza wyjatkami."""
    assert spec["security"] == [{"bearerAuth": []}]


def test_wszystkie_odwolania_wewnetrzne_istnieja(spec):
    """Kazde $ref musi wskazywac istniejacy element — inaczej dokumentacja sie nie wyswietli."""
    brakujace = []

    def sprawdz(wezel):
        if isinstance(wezel, dict):
            for klucz, wartosc in wezel.items():
                if klucz == "$ref" and isinstance(wartosc, str):
                    cel = spec
                    for czesc in wartosc.lstrip("#/").split("/"):
                        cel = cel.get(czesc) if isinstance(cel, dict) else None
                        if cel is None:
                            brakujace.append(wartosc)
                            break
                else:
                    sprawdz(wartosc)
        elif isinstance(wezel, list):
            for element in wezel:
                sprawdz(element)

    sprawdz(spec)
    assert not brakujace, f"Nieistniejace odwolania: {sorted(set(brakujace))}"


# ---------------------------------------------------------------
# Zgodnosc: specyfikacja <-> zarejestrowane trasy
# ---------------------------------------------------------------

def test_kazdy_endpoint_api_jest_udokumentowany(app, spec):
    """Nowa trasa bez wpisu w specyfikacji ma zatrzymac budowanie."""
    brakujace = set(_sciezki_flaska(app)) - set(_sciezki_specyfikacji(spec))
    assert not brakujace, f"Trasy bez dokumentacji: {sorted(brakujace)}"


def test_specyfikacja_nie_opisuje_nieistniejacych_endpointow(app, spec):
    """Usunieta trasa musi zniknac takze ze specyfikacji."""
    zbedne = set(_sciezki_specyfikacji(spec)) - set(_sciezki_flaska(app))
    assert not zbedne, f"Udokumentowane, ale nieistniejace: {sorted(zbedne)}"


def test_metody_http_sie_zgadzaja(app, spec):
    flask_sciezki = _sciezki_flaska(app)
    spec_sciezki = _sciezki_specyfikacji(spec)
    roznice = {
        sciezka: {"kod": sorted(metody), "specyfikacja": sorted(spec_sciezki.get(sciezka, set()))}
        for sciezka, metody in flask_sciezki.items()
        if metody != spec_sciezki.get(sciezka, set())
    }
    assert not roznice, f"Rozjazd metod HTTP: {roznice}"


def test_tylko_wyznaczone_operacje_sa_publiczne(spec):
    """Zamkniety zbior operacji bez tokenu.

    Publiczne moga byc wylacznie dwie rzeczy i obie z konkretnego powodu:
    logowanie (token dopiero powstaje) oraz kontrola zdrowia (sonda load
    balancera nie ma tokenu). Kazda inna operacja dziedziczy wymog autoryzacji
    — dopisanie kolejnej zatrzyma ten test.
    """
    dozwolone = {"POST /auth/login", "GET /health"}

    publiczne = {
        f"{metoda.upper()} {sciezka}"
        for sciezka, operacje in spec["paths"].items()
        for metoda, opis in operacje.items()
        if metoda in {"get", "post", "put", "patch", "delete"} and opis.get("security") == []
    }
    assert publiczne == dozwolone, f"Nieoczekiwane operacje publiczne: {publiczne ^ dozwolone}"


def test_health_faktycznie_dziala_bez_tokenu(client):
    """Deklaracja w specyfikacji musi zgadzac sie z zachowaniem aplikacji."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_health_nie_ujawnia_szczegolow_systemu(client):
    """Endpoint bez autoryzacji nie moze zdradzac wersji, sciezek ani liczb."""
    dane = client.get("/api/health").get_json()
    assert set(dane) == {"status"}


# ---------------------------------------------------------------
# Zgodnosc: slowniki wartosci <-> stale w kodzie
# ---------------------------------------------------------------

def test_lista_statusow_odpowiada_maszynie_stanow(spec):
    assert set(spec["components"]["schemas"]["Status"]["enum"]) == set(TRANSITIONS)


def test_lista_kategorii_odpowiada_modulowi_ai(spec):
    assert set(spec["components"]["schemas"]["Kategoria"]["enum"]) == set(CATEGORIES)


def test_lista_priorytetow_odpowiada_tabeli_sla(spec):
    assert set(spec["components"]["schemas"]["Priorytet"]["enum"]) == set(SLA_HOURS)


def test_lista_rol_odpowiada_schematowi_bazy(spec):
    """Role sa ograniczone warunkiem CHECK w schemacie tabeli users."""
    dozwolone = set(re.findall(r"role\s+TEXT\s+NOT NULL\s+CHECK\(role IN \(([^)]+)\)",
                               database.SCHEMA)[0].replace("'", "").split(","))
    assert set(spec["components"]["schemas"]["Rola"]["enum"]) == {r.strip() for r in dozwolone}


# ---------------------------------------------------------------
# Zgodnosc: schematy <-> rzeczywiste odpowiedzi API
# ---------------------------------------------------------------

def _wlasciwosci(spec, nazwa):
    return set(spec["components"]["schemas"][nazwa]["properties"])


def test_schemat_zgloszenia_odpowiada_odpowiedzi_listy(client, technik, spec):
    zgloszenie = client.get("/api/tickets", headers=technik).get_json()["tickets"][0]
    assert set(zgloszenie) == _wlasciwosci(spec, "Zgloszenie")


def test_schemat_zgloszenia_odpowiada_odpowiedzi_szczegolow(client, technik, spec):
    dane = client.get("/api/tickets/1", headers=technik).get_json()
    assert set(dane) - {"notes"} == _wlasciwosci(spec, "Zgloszenie")


def test_wszystkie_pola_zgloszenia_sa_wymagane_w_schemacie(spec):
    """Klient moze polegac na obecnosci pol — brak w 'required' bylby mylacy."""
    schemat = spec["components"]["schemas"]["Zgloszenie"]
    assert set(schemat["required"]) == set(schemat["properties"])


def test_schemat_notatki_odpowiada_odpowiedzi(client, technik, spec):
    notatka = client.get("/api/tickets/1", headers=technik).get_json()["notes"][0]
    assert set(notatka) == _wlasciwosci(spec, "Notatka")


def test_schemat_audytu_odpowiada_odpowiedzi(client, technik, spec):
    client.patch("/api/tickets/1", headers=technik, json={"status": "W trakcie"})
    wpis = client.get("/api/tickets/1/audit", headers=technik).get_json()[0]
    assert set(wpis) == _wlasciwosci(spec, "WpisAudytu")


def test_schemat_wyniku_ai_odpowiada_odpowiedzi(client, pracownik, spec):
    wynik = client.post("/api/ai/categorize", headers=pracownik,
                        json={"title": "phishing"}).get_json()
    assert set(wynik) == _wlasciwosci(spec, "WynikAI")


def test_schemat_logowania_odpowiada_odpowiedzi(client, spec):
    dane = client.post("/api/auth/login",
                       json={"username": "k.nowak", "password": "haslo123"}).get_json()
    schemat = spec["paths"]["/auth/login"]["post"]["responses"]["200"]
    assert set(dane) == set(schemat["content"]["application/json"]["schema"]["properties"])


def test_udokumentowane_limity_dlugosci_odpowiadaja_walidacji(spec):
    """Limity w dokumentacji musza byc tymi samymi, ktore egzekwuje kod."""
    from app import config

    body = spec["paths"]["/tickets"]["post"]["requestBody"]["content"]["application/json"]
    wlasciwosci = body["schema"]["properties"]
    assert wlasciwosci["title"]["maxLength"] == config.TITLE_MAX
    assert wlasciwosci["description"]["maxLength"] == config.DESC_MAX

    notatka = spec["paths"]["/tickets/{ticket_id}/notes"]["post"]["requestBody"]
    schemat_notatki = notatka["content"]["application/json"]["schema"]["properties"]
    assert schemat_notatki["content"]["maxLength"] == config.NOTE_MAX


# ---------------------------------------------------------------
# Dostepnosc dokumentacji przez HTTP
# ---------------------------------------------------------------

def test_specyfikacja_jest_serwowana(client):
    resp = client.get("/api/openapi.yaml")
    assert resp.status_code == 200
    assert b"openapi:" in resp.data


def test_serwowana_specyfikacja_jest_tym_samym_plikiem(client, spec):
    assert yaml.safe_load(client.get("/api/openapi.yaml").data) == spec


def test_interaktywna_dokumentacja_odpowiada(client):
    resp = client.get("/api/docs/")
    assert resp.status_code == 200
    assert b"swagger" in resp.data.lower()


def test_dokumentacja_nie_wymaga_zewnetrznego_cdn(client):
    """Zasoby Swagger UI musza pochodzic z tego serwera — inaczej CSP je zablokuje."""
    tresc = client.get("/api/docs/").get_data(as_text=True)
    for zewnetrzny in ("unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com"):
        assert zewnetrzny not in tresc


def test_dokumentacja_nie_przeslania_endpointow_api(client, technik):
    """Trasy dokumentacji nie moga przechwytywac wlasciwego API."""
    assert client.get("/api/tickets", headers=technik).status_code == 200
    assert client.get("/api/nieistniejacy").status_code == 404


# ---------------------------------------------------------------
# Tabela skrotowa w README
# ---------------------------------------------------------------

def test_tabela_w_readme_odpowiada_specyfikacji(spec):
    """README zawiera skrocona tabele endpointow — to ona rozjechala sie wczesniej.

    Test porownuje ja ze specyfikacja, wiec nieaktualny wiersz zatrzyma budowanie.
    """
    readme = os.path.join(os.path.dirname(SPEC_PATH), "README.md")
    with open(readme, encoding="utf-8") as f:
        tresc = f.read()

    # Wiersze postaci: | POST | `/api/tickets/{id}` | rola | opis |
    wiersze = re.findall(
        r"^\|\s*(GET|POST|PATCH|PUT|DELETE)\s*\|\s*`(/api[^`]*)`", tresc, re.MULTILINE
    )
    assert wiersze, "Nie znaleziono tabeli endpointow w README"

    # README uzywa skrotu {id}; specyfikacja pelnej nazwy parametru {ticket_id}.
    z_readme = {
        (metoda.lower(), sciezka[len("/api"):].replace("{id}", "{ticket_id}"))
        for metoda, sciezka in wiersze
    }
    ze_specyfikacji = {
        (metoda, sciezka)
        for sciezka, metody in _sciezki_specyfikacji(spec).items()
        for metoda in metody
    }

    assert z_readme == ze_specyfikacji, (
        f"Tabela w README rozjechala sie ze specyfikacja.\n"
        f"  tylko w README: {sorted(z_readme - ze_specyfikacji)}\n"
        f"  tylko w openapi.yaml: {sorted(ze_specyfikacji - z_readme)}"
    )
