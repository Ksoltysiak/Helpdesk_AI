"""Testy zmian wydajnosciowych: stronicowanie, indeksy, kompresja,
naglowki cache i kontrola zdrowia.

Nie mierza czasu (to bylo by kruche na wspoldzielonym CI), tylko sprawdzaja,
ze mechanizmy sa faktycznie wlaczone i poprawne.
"""

import sqlite3

import pytest

import db as db_module

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------
# Stronicowanie
# ---------------------------------------------------------------

def test_odpowiedz_zawiera_dane_stronicowania(client, technik):
    dane = client.get("/api/tickets", headers=technik).get_json()
    assert set(dane) == {"total", "page", "per_page", "pages", "tickets"}


def test_domyslnie_pierwsza_strona_po_50(client, technik):
    dane = client.get("/api/tickets", headers=technik).get_json()
    assert dane["page"] == 1
    assert dane["per_page"] == 50


def test_total_liczy_wszystkie_pasujace_nie_zwrocone(client, technik):
    """Przy 4 zgloszeniach i per_page=2 total musi nadal wynosic 4."""
    dane = client.get("/api/tickets?per_page=2", headers=technik).get_json()
    assert dane["total"] == 4
    assert len(dane["tickets"]) == 2
    assert dane["pages"] == 2


def test_druga_strona_zwraca_pozostale_zgloszenia(client, technik):
    s1 = client.get("/api/tickets?per_page=2&page=1", headers=technik).get_json()
    s2 = client.get("/api/tickets?per_page=2&page=2", headers=technik).get_json()
    id1 = {t["id"] for t in s1["tickets"]}
    id2 = {t["id"] for t in s2["tickets"]}
    assert not (id1 & id2), "Strony nie moga sie pokrywac"
    assert id1 | id2 == {1, 2, 3, 4}, "Razem musza dac komplet zgloszen"


def test_strony_nie_gubia_zgloszen_przy_kazdym_rozmiarze(client, technik):
    for per_page in (1, 2, 3, 4, 5):
        zebrane = set()
        strona = 1
        while True:
            dane = client.get(f"/api/tickets?per_page={per_page}&page={strona}",
                              headers=technik).get_json()
            zebrane |= {t["id"] for t in dane["tickets"]}
            if strona >= dane["pages"]:
                break
            strona += 1
        assert zebrane == {1, 2, 3, 4}, f"Zgubiono zgloszenia przy per_page={per_page}"


@pytest.mark.parametrize("zapytanie,oczekiwane", [
    ("per_page=9999", 200),   # przyciete do maksimum
    ("per_page=0", 1),        # przyciete do minimum
    ("per_page=-5", 1),
    ("per_page=abc", 50),     # nieliczbowe -> wartosc domyslna
    ("per_page=", 50),
])
def test_per_page_jest_ograniczane_do_dozwolonego_zakresu(client, technik, zapytanie, oczekiwane):
    """Bez gornego limitu jedno zadanie moglo by pobrac cala baze."""
    dane = client.get(f"/api/tickets?{zapytanie}", headers=technik).get_json()
    assert dane["per_page"] == oczekiwane


@pytest.mark.parametrize("zapytanie", ["page=0", "page=-3", "page=abc", "page=99999"])
def test_bledny_numer_strony_nie_powoduje_bledu(client, technik, zapytanie):
    resp = client.get(f"/api/tickets?{zapytanie}", headers=technik)
    assert resp.status_code == 200
    assert 1 <= resp.get_json()["page"] <= resp.get_json()["pages"]


def test_stronicowanie_nie_omija_izolacji_pracownika(client, pracownik):
    """Kluczowe: przewijanie stron nie moze odslonic cudzych zgloszen."""
    strona = 1
    while True:
        dane = client.get(f"/api/tickets?per_page=1&page={strona}", headers=pracownik).get_json()
        assert all(t["created_by"] == 1 for t in dane["tickets"])
        if strona >= dane["pages"]:
            break
        strona += 1


def test_pusta_lista_ma_poprawne_stronicowanie(client, technik):
    """Filtr bez wynikow: pages nie moze byc zerem ani ujemne."""
    dane = client.get("/api/tickets?status=Wstrzymane", headers=technik).get_json()
    assert dane["total"] == 0
    assert dane["tickets"] == []
    assert dane["pages"] == 1
    assert dane["page"] == 1


# ---------------------------------------------------------------
# Indeksy
# ---------------------------------------------------------------

def test_baza_ma_utworzone_indeksy(app):
    conn = sqlite3.connect(db_module.DB_PATH)
    indeksy = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")}
    conn.close()
    assert "idx_tickets_created_by" in indeksy
    assert "idx_tickets_status" in indeksy
    assert "idx_notes_ticket" in indeksy


def test_filtrowanie_korzysta_z_indeksu(app):
    """Plan zapytania musi pokazac uzycie indeksu, a nie skan calej tabeli."""
    conn = sqlite3.connect(db_module.DB_PATH)
    plan = " ".join(str(r) for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM tickets WHERE status = 'Nowe'").fetchall())
    conn.close()
    assert "USING INDEX" in plan.upper(), f"Brak uzycia indeksu: {plan}"


def test_lista_pracownika_korzysta_z_indeksu(app):
    conn = sqlite3.connect(db_module.DB_PATH)
    plan = " ".join(str(r) for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM tickets WHERE created_by = 1 ORDER BY id DESC"
    ).fetchall())
    conn.close()
    assert "USING INDEX" in plan.upper(), f"Brak uzycia indeksu: {plan}"


def test_init_db_mozna_wywolac_wielokrotnie(app):
    """Uruchamiane przy kazdym starcie kontenera — musi byc idempotentne."""
    db_module.init_db()
    db_module.init_db()
    conn = sqlite3.connect(db_module.DB_PATH)
    liczba = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    assert liczba == 4, "Ponowna inicjalizacja nie moze dublowac ani kasowac danych"


def test_baza_dziala_w_trybie_wal(app):
    conn = sqlite3.connect(db_module.DB_PATH)
    tryb = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert tryb.lower() == "wal", "WAL pozwala czytac w trakcie zapisu"


# ---------------------------------------------------------------
# Pulpit po zmianie na jedno zapytanie
# ---------------------------------------------------------------

def test_pulpit_technika_liczy_wszystkie_zgloszenia(client, technik):
    stat = client.get("/api/dashboard", headers=technik).get_json()["statystyki"]
    assert stat == {"wszystkie": 4, "otwarte": 3, "w_trakcie": 1,
                    "rozwiazane": 0, "zamkniete": 1, "krytyczne": 1}


def test_pulpit_pracownika_liczy_tylko_jego_zgloszenia(client, pracownik):
    """Pracownik ma 2 zgloszenia (#1 Nowe/Krytyczny, #2 W trakcie) z 4 w systemie."""
    stat = client.get("/api/dashboard", headers=pracownik).get_json()["statystyki"]
    assert stat["wszystkie"] == 2
    assert stat["otwarte"] == 2
    assert stat["zamkniete"] == 0


def test_pulpit_nie_ujawnia_pracownikowi_skali_systemu(client, pracownik, technik):
    """Liczby pracownika musza byc mniejsze niz calego systemu."""
    prac = client.get("/api/dashboard", headers=pracownik).get_json()
    tech = client.get("/api/dashboard", headers=technik).get_json()
    assert prac["statystyki"]["wszystkie"] < tech["statystyki"]["wszystkie"]


def test_rozklad_kategorii_tez_jest_ograniczony_rola(client, pracownik, technik):
    prac = client.get("/api/dashboard", headers=pracownik).get_json()["wg_kategorii"]
    tech = client.get("/api/dashboard", headers=technik).get_json()["wg_kategorii"]
    assert sum(k["liczba"] for k in prac) == 2
    assert sum(k["liczba"] for k in tech) == 4


def test_pulpit_pracownika_zgadza_sie_z_jego_lista(client, pracownik):
    """Licznik na pulpicie i total listy musza pokazywac to samo."""
    stat = client.get("/api/dashboard", headers=pracownik).get_json()["statystyki"]
    lista = client.get("/api/tickets", headers=pracownik).get_json()
    assert stat["wszystkie"] == lista["total"]


def test_pulpit_na_pustej_bazie_pokazuje_zera(client, technik, app):
    """SUM() zwraca NULL dla pustej tabeli — pulpit ma pokazac 0, nie null."""
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("DELETE FROM audit_log")
    conn.execute("DELETE FROM notes")
    conn.execute("DELETE FROM tickets")
    conn.commit()
    conn.close()

    stat = client.get("/api/dashboard", headers=technik).get_json()["statystyki"]
    assert stat == {"wszystkie": 0, "otwarte": 0, "w_trakcie": 0,
                    "rozwiazane": 0, "zamkniete": 0, "krytyczne": 0}


# ---------------------------------------------------------------
# Kompresja
# ---------------------------------------------------------------

def test_duza_odpowiedz_jest_kompresowana(client, technik):
    """Lista zgloszen przekracza prog kompresji, wiec musi wrocic spakowana."""
    resp = client.get("/api/tickets", headers={**technik, "Accept-Encoding": "gzip"})
    assert resp.headers.get("Content-Encoding") == "gzip"
    assert "Accept-Encoding" in resp.headers.get("Vary", "")


def test_kompresja_realnie_zmniejsza_odpowiedz(client, technik):
    zwykla = client.get("/api/tickets", headers={**technik, "Accept-Encoding": ""})
    spakowana = client.get("/api/tickets", headers={**technik, "Accept-Encoding": "gzip"})
    assert len(spakowana.get_data()) < len(zwykla.get_data())


def test_bez_naglowka_accept_encoding_nie_kompresujemy(client, technik):
    resp = client.get("/api/tickets", headers={**technik, "Accept-Encoding": ""})
    assert "Content-Encoding" not in resp.headers


def test_kompresja_zachowuje_tresc(client, technik):
    """Po rozpakowaniu tresc musi byc identyczna — kompresja nie moze gubic danych."""
    import gzip
    import json

    zwykla = client.get("/api/tickets", headers={**technik, "Accept-Encoding": ""})
    spakowana = client.get("/api/tickets", headers={**technik, "Accept-Encoding": "gzip"})

    rozpakowana = json.loads(gzip.decompress(spakowana.get_data()))
    assert rozpakowana == zwykla.get_json()


def test_male_odpowiedzi_nie_sa_kompresowane(client):
    """Ponizej progu narzut gzip przewaza nad zyskiem."""
    resp = client.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in resp.headers


# ---------------------------------------------------------------
# Naglowki cache
# ---------------------------------------------------------------

def test_odpowiedzi_api_nie_sa_cache_owane(client, technik):
    """Dane zgloszen w cache przegladarki mogłyby trafic do kolejnej osoby."""
    assert client.get("/api/tickets", headers=technik).headers["Cache-Control"] == "no-store"


def test_dane_logowania_nie_sa_cache_owane(client):
    resp = client.post("/api/auth/login", json={"username": "k.nowak", "password": "haslo123"})
    assert resp.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("plik", ["/style.css", "/script.js"])
def test_pliki_statyczne_maja_naglowek_cache(client, plik):
    cache = client.get(plik).headers.get("Cache-Control", "")
    assert "max-age" in cache and "must-revalidate" in cache


def test_strona_glowna_nie_jest_cache_owana_na_stale(client):
    """index.html musi byc pobierany na nowo, inaczej aktualizacja nie dotrze."""
    assert "max-age=3600" not in client.get("/").headers.get("Cache-Control", "")


# ---------------------------------------------------------------
# Kontrola zdrowia
# ---------------------------------------------------------------

def test_health_dziala_bez_autoryzacji(client):
    assert client.get("/api/health").status_code == 200


def test_health_nie_podlega_limitowi_zadan(rate_limited_client):
    """Sonda odpytuje czesto — limit nie moze jej blokowac."""
    kody = [rate_limited_client.get("/api/health").status_code for _ in range(40)]
    assert all(k == 200 for k in kody)


def test_health_zglasza_503_gdy_baza_nie_odpowiada(client, monkeypatch):
    """Sonda ma wykryc awarie bazy, a nie raportowac 'ok' mimo problemu."""
    import routes

    def zepsuta_baza():
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(routes, "get_db", zepsuta_baza)

    resp = client.get("/api/health")
    assert resp.status_code == 503
    assert resp.get_json() == {"status": "error"}


def test_health_nie_ujawnia_przyczyny_awarii(client, monkeypatch):
    """Komunikat bledu bazy nie moze trafic do niezalogowanego klienta."""
    import routes

    def zepsuta_baza():
        raise sqlite3.OperationalError("/tajna/sciezka/helpdesk.db is locked")

    monkeypatch.setattr(routes, "get_db", zepsuta_baza)

    tresc = client.get("/api/health").get_data(as_text=True)
    assert "tajna" not in tresc and "locked" not in tresc


# ---------------------------------------------------------------
# Kompresja: przypadki brzegowe
# ---------------------------------------------------------------

def test_odpowiedz_bledu_nie_jest_kompresowana(client):
    """Kompresujemy tylko udane odpowiedzi — blad i tak jest krotki."""
    resp = client.get("/api/nieistniejacy", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 404
    assert "Content-Encoding" not in resp.headers


def test_typ_spoza_listy_nie_jest_kompresowany(app):
    """Obrazy i archiwa sa juz skompresowane — pakowanie ich tylko kosztuje CPU."""
    @app.route("/api/_obraz_testowy")
    def obraz():
        from flask import Response
        return Response(b"\x89PNG" + b"\x00" * 5000, mimetype="image/png")

    resp = app.test_client().get("/api/_obraz_testowy", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    assert "Content-Encoding" not in resp.headers


def test_typ_tekstowy_z_listy_jest_kompresowany(app):
    """Kontrola pozytywna dla tej samej sciezki decyzyjnej."""
    @app.route("/api/_tekst_testowy")
    def tekst():
        from flask import Response
        return Response("x" * 5000, mimetype="application/json")

    resp = app.test_client().get("/api/_tekst_testowy", headers={"Accept-Encoding": "gzip"})
    assert resp.headers.get("Content-Encoding") == "gzip"
