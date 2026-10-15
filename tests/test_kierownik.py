"""Testy roli kierownika: przydzial pracy, statystyki zespolu, kolejka, SLA.

Statystyki sprawdzane sa na danych z marca 2026 (zawsze w przeszlosci).
Technik 3 i technik 5 pracuja przy zgloszeniach klienta 1:

  id   utworzono      podjal (godz.)   rozwiazal (godz.)        status teraz   termin SLA
  301  03-02 08:00    3 o 09:00 (1 h)  3 o 11:00 (3 h)          Zamkniete      12:00 -> w terminie
  302  03-03T08:00    5 o 12:00 (4 h)  5 o 20:00 (12 h)         Rozwiazane     16:00 -> po terminie
  303  03-05 08:00    3 o 08:30 (0,5)  3 o 10:00, otwarte przez 5,
                                       5 o 14:00 (6 h)          Zamkniete      16:00 -> w terminie
  304  03-10 08:00    3 o 08:30 (0,5)  3 o 09:00, otwarte ponownie W trakcie (3), termin minal
  305  02-20 08:00    3 (luty)         3 o 10:00 (luty)         Zamkniete      — okres poprzedni
  306  03-31 20:00    3 o 21:00 (1 h)  3 — 04-01 00:00:00       Zamkniete      — poza okresem

Oczekiwane wyniki za marzec:
  technik 3: podjetych 4 (srednio 0,75 h), rozwiazanych 1 (301: 3 h, w terminie),
             poprzednio 1 (305), notatek 1, otwartych teraz 2 (zgl. 2 i 304), obie po terminie
  technik 5: podjetych 1 (4 h), rozwiazanych 2 (302: 12 h po terminie, 303: 6 h w terminie)
             -> srednio 9 h, 50% w terminie, notatek 1 (druga jest z kwietnia)
"""

import sqlite3
from datetime import datetime

import pytest

from app import config as db_module

pytestmark = pytest.mark.integration

MARZEC = "od=2026-03-01&do=2026-03-31"


def _zgloszenie(conn, tid, utworzono, kategoria, status, *, przypisany=None, termin=None):
    conn.execute(
        """INSERT INTO tickets (id, title, description, category, priority, status,
                                created_by, assigned_to, client_id, ai_categorized,
                                sla_deadline, created_at, updated_at)
           VALUES (?,?,?,?,'Sredni',?,1,?,1,1,?,?,?)""",
        (tid, f"Zgloszenie {tid}", "opis", kategoria, status, przypisany, termin,
         utworzono, utworzono))


def _status(conn, tid, kto, stary, nowy, kiedy):
    conn.execute(
        "INSERT INTO audit_log (ticket_id, user_id, action, old_value, new_value, timestamp)"
        " VALUES (?,?,'Zmiana statusu',?,?,?)", (tid, kto, stary, nowy, kiedy))


@pytest.fixture
def praca(app):
    conn = sqlite3.connect(db_module.DB_PATH)
    _zgloszenie(conn, 301, "2026-03-02 08:00:00", "Siec", "Zamkniete", przypisany=3,
                termin="2026-03-02 12:00:00")
    _status(conn, 301, 3, "Nowe", "W trakcie", "2026-03-02 09:00:00")
    _status(conn, 301, 3, "W trakcie", "Rozwiazane", "2026-03-02 11:00:00")

    _zgloszenie(conn, 302, "2026-03-03T08:00:00", "Poczta", "Rozwiazane", przypisany=5,
                termin="2026-03-03 16:00:00")
    _status(conn, 302, 5, "Nowe", "W trakcie", "2026-03-03 12:00:00")
    _status(conn, 302, 5, "W trakcie", "Rozwiazane", "2026-03-03 20:00:00")

    _zgloszenie(conn, 303, "2026-03-05 08:00:00", "Sprzet", "Zamkniete", przypisany=5,
                termin="2026-03-05 16:00:00")
    _status(conn, 303, 3, "Nowe", "W trakcie", "2026-03-05 08:30:00")
    _status(conn, 303, 3, "W trakcie", "Rozwiazane", "2026-03-05 10:00:00")
    _status(conn, 303, 5, "Rozwiazane", "W trakcie", "2026-03-05 12:00:00")
    _status(conn, 303, 5, "W trakcie", "Rozwiazane", "2026-03-05 14:00:00")

    _zgloszenie(conn, 304, "2026-03-10 08:00:00", "Siec", "W trakcie", przypisany=3,
                termin="2026-03-10 12:00:00")
    _status(conn, 304, 3, "Nowe", "W trakcie", "2026-03-10 08:30:00")
    _status(conn, 304, 3, "W trakcie", "Rozwiazane", "2026-03-10 09:00:00")
    _status(conn, 304, 3, "Rozwiazane", "W trakcie", "2026-03-10 10:00:00")

    _zgloszenie(conn, 305, "2026-02-20 08:00:00", "Siec", "Zamkniete", przypisany=3)
    _status(conn, 305, 3, "Nowe", "W trakcie", "2026-02-20 09:00:00")
    _status(conn, 305, 3, "W trakcie", "Rozwiazane", "2026-02-20 10:00:00")

    _zgloszenie(conn, 306, "2026-03-31 20:00:00", "Siec", "Zamkniete", przypisany=3)
    _status(conn, 306, 3, "Nowe", "W trakcie", "2026-03-31 21:00:00")
    _status(conn, 306, 3, "W trakcie", "Rozwiazane", "2026-04-01 00:00:00")

    for autor, kiedy in ((3, "2026-03-04 10:00:00"), (5, "2026-03-04 11:00:00"),
                         (5, "2026-04-02 11:00:00")):
        conn.execute("INSERT INTO notes (ticket_id, author_id, content, created_at)"
                     " VALUES (301, ?, 'notatka', ?)", (autor, kiedy))
    conn.commit()
    conn.close()


def _get(client, naglowki, sciezka):
    resp = client.get(sciezka, headers=naglowki)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


# ---------------------------------------------------------------
# Rola
# ---------------------------------------------------------------

def test_kierownik_obsluguje_zgloszenia_jak_technik(client, kierownik):
    assert client.get("/api/tickets", headers=kierownik).get_json()["total"] == 4
    assert client.patch("/api/tickets/1", headers=kierownik,
                        json={"status": "W trakcie"}).status_code == 200
    assert client.get("/api/tickets/1/audit", headers=kierownik).status_code == 200


def test_logowanie_kierownika(client):
    dane = client.post("/api/auth/login",
                       json={"username": "t.adamski", "password": "kierownik123"}).get_json()
    assert dane["role"] == "kierownik"


def test_baza_nie_przyjmuje_roli_admin(app):
    conn = sqlite3.connect(db_module.DB_PATH)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO users (username, password, name, role)"
                     " VALUES ('x', 'h', 'X', 'admin')")
    conn.close()


# ---------------------------------------------------------------
# Przydzial pracy
# ---------------------------------------------------------------

def test_technik_bierze_wolne_zgloszenie(client, technik):
    resp = client.patch("/api/tickets/1", headers=technik, json={"assigned_to": 3})
    assert resp.status_code == 200
    assert client.get("/api/tickets/1", headers=technik).get_json()["assigned_to"] == 3


def test_technik_nie_przydziela_pracy_innym(client, technik):
    resp = client.patch("/api/tickets/1", headers=technik, json={"assigned_to": 5})
    assert resp.status_code == 403


def test_technik_nie_przejmuje_cudzego_zgloszenia(client, technik2):
    """Zgloszenie 2 prowadzi technik 3 — technik 5 nie moze go sobie zabrac."""
    resp = client.patch("/api/tickets/2", headers=technik2, json={"assigned_to": 5})
    assert resp.status_code == 403


def test_technik_nie_zwalnia_przypisania(client, technik):
    resp = client.patch("/api/tickets/2", headers=technik, json={"assigned_to": None})
    assert resp.status_code == 403


def test_kierownik_przenosi_zgloszenie_miedzy_technikami(client, kierownik):
    assert client.patch("/api/tickets/2", headers=kierownik,
                        json={"assigned_to": 5}).status_code == 200
    audyt = client.get("/api/tickets/2/audit", headers=kierownik).get_json()
    wpis = next(w for w in audyt if w["action"] == "Przypisanie")
    assert (wpis["old"], wpis["new"], wpis["user"]) == ("3", "5", "Tomasz Adamski")


def test_kierownik_zwalnia_przypisanie(client, kierownik):
    assert client.patch("/api/tickets/2", headers=kierownik,
                        json={"assigned_to": None}).status_code == 200
    assert client.get("/api/tickets/2", headers=kierownik).get_json()["assigned_to"] is None
    wpis = next(w for w in client.get("/api/tickets/2/audit", headers=kierownik).get_json()
                if w["action"] == "Przypisanie")
    assert wpis["new"] is None


def test_kierownik_moze_przypisac_siebie(client, kierownik):
    assert client.patch("/api/tickets/1", headers=kierownik,
                        json={"assigned_to": 4}).status_code == 200


def test_dwoch_technikow_bierze_to_samo_zgloszenie(client, technik, monkeypatch, app):
    """Technik 5 byl szybszy; technik 3 dziala na nieaktualnym odczycie."""
    from app.data import tickets as repo
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("UPDATE tickets SET assigned_to = 5 WHERE id = 1")
    conn.commit()
    conn.close()
    prawdziwe = repo.pobierz_surowe
    monkeypatch.setattr(repo, "pobierz_surowe",
                        lambda tid: {**prawdziwe(tid), "assigned_to": None})

    resp = client.patch("/api/tickets/1", headers=technik,
                        json={"status": "W trakcie", "assigned_to": 3})
    assert resp.status_code == 409
    monkeypatch.setattr(repo, "pobierz_surowe", prawdziwe)
    stan = client.get("/api/tickets/1", headers=technik).get_json()
    # Zmiana statusu z tego samego zadania tez nie zostala zapisana.
    assert (stan["assigned_to"], stan["status"]) == (5, "Nowe")


# ---------------------------------------------------------------
# Raporty klientow — zakres technika
# ---------------------------------------------------------------

def test_technik_tworzy_raport_obslugiwanej_firmy(client, technik):
    assert client.get("/api/reports?client_id=1", headers=technik).status_code == 200


def test_technik_nie_tworzy_raportu_cudzej_firmy(client, technik):
    resp = client.get("/api/reports?client_id=2", headers=technik)
    assert resp.status_code == 403


def test_raport_zbiorczy_tylko_dla_kierownika(client, technik, kierownik):
    assert client.get("/api/reports", headers=technik).status_code == 403
    assert client.get("/api/reports", headers=kierownik).status_code == 200


def test_kierownik_tworzy_raport_dowolnej_firmy(client, kierownik):
    for klient in (1, 2, 3):
        assert client.get(f"/api/reports?client_id={klient}", headers=kierownik).status_code == 200


def test_lista_klientow_wskazuje_obslugiwane_firmy(client, technik, technik2, kierownik):
    def obslugiwane(naglowki):
        return {k["id"] for k in client.get("/api/clients", headers=naglowki).get_json()
                if k["obslugiwany"]}
    assert obslugiwane(technik) == {1, 3}
    assert obslugiwane(technik2) == {2}
    assert obslugiwane(kierownik) == {1, 2, 3}


# ---------------------------------------------------------------
# Statystyki zespolu
# ---------------------------------------------------------------

@pytest.mark.parametrize("rola", ["pracownik", "technik"])
def test_statystyki_zespolu_tylko_dla_kierownika(client, request, rola):
    assert client.get("/api/team", headers=request.getfixturevalue(rola)).status_code == 403


def test_statystyki_zespolu(client, kierownik, praca):
    dane = _get(client, kierownik, f"/api/team?{MARZEC}")
    technicy = {t["id"]: t for t in dane["technicy"]}
    assert set(technicy) == {3, 4, 5}

    t3 = technicy[3]
    assert (t3["podjetych"], t3["sredni_czas_reakcji_h"]) == (4, 0.8)
    assert (t3["rozwiazanych"], t3["sredni_czas_rozwiazania_h"]) == (1, 3.0)
    assert (t3["rozwiazanych_poprzednio"], t3["zmiana_proc"]) == (1, 0.0)
    assert t3["procent_w_terminie_sla"] == 100.0
    assert (t3["otwartych"], t3["otwartych_po_terminie"], t3["notatek"]) == (2, 2, 1)

    t5 = technicy[5]
    assert (t5["podjetych"], t5["sredni_czas_reakcji_h"]) == (1, 4.0)
    assert (t5["rozwiazanych"], t5["sredni_czas_rozwiazania_h"]) == (2, 9.0)
    assert (t5["w_terminie_sla"], t5["procent_w_terminie_sla"]) == (1, 50.0)
    assert (t5["zmiana_proc"], t5["notatek"], t5["otwartych"]) == (None, 1, 0)

    assert technicy[4]["rozwiazanych"] == 0 and technicy[4]["role"] == "kierownik"


def test_suma_zespolu(client, kierownik, praca):
    zespol = _get(client, kierownik, f"/api/team?{MARZEC}")["zespol"]
    assert (zespol["podjetych"], zespol["rozwiazanych"]) == (5, 3)
    assert zespol["sredni_czas_rozwiazania_h"] == 7.0        # (3 + 2 * 9) / 3
    assert zespol["procent_w_terminie_sla"] == 66.7
    assert (zespol["rozwiazanych_poprzednio"], zespol["zmiana_proc"]) == (1, 200.0)


def test_rozwiazanie_liczy_sie_temu_kto_rozwiazal_ostatni(client, kierownik, praca):
    """303: pierwszy „rozwiazal" technik 3, ale zgloszenie wrocilo — liczy sie technik 5."""
    t3 = _get(client, kierownik, "/api/team/3?od=2026-03-05&do=2026-03-05")["statystyki"]
    t5 = _get(client, kierownik, "/api/team/5?od=2026-03-05&do=2026-03-05")["statystyki"]
    assert (t3["rozwiazanych"], t5["rozwiazanych"]) == (0, 1)


def test_ponownie_otwarte_zgloszenie_nie_jest_rozwiazaniem(client, kierownik, praca):
    t3 = _get(client, kierownik, "/api/team/3?od=2026-03-10&do=2026-03-10")["statystyki"]
    assert t3["rozwiazanych"] == 0 and t3["podjetych"] == 1


def test_granica_okresu_dla_rozwiazan(client, kierownik, praca):
    """306 rozwiazano o 00:00:00 1 kwietnia — to juz kwiecien."""
    kwiecien = _get(client, kierownik, "/api/team/3?od=2026-04-01&do=2026-04-01")["statystyki"]
    assert kwiecien["rozwiazanych"] == 1


# ---------------------------------------------------------------
# Raport technika — wlasny albo dla kierownika
# ---------------------------------------------------------------

def test_technik_widzi_wlasne_statystyki(client, technik2, praca):
    dane = _get(client, technik2, f"/api/team/5?{MARZEC}")
    assert dane["technik"] == {"id": 5, "name": "Joanna Zielinska", "role": "technik"}
    assert dane["statystyki"]["rozwiazanych"] == 2
    assert {t["okres"]: t["liczba"] for t in dane["trend"] if t["liczba"]} == {
        "2026-03-03": 1, "2026-03-05": 1}
    assert dane["wg_kategorii"] == [
        {"kategoria": "Poczta", "etykieta": "Poczta", "liczba": 1},
        {"kategoria": "Sprzet", "etykieta": "Sprzęt", "liczba": 1},
    ]


def test_technik_nie_widzi_statystyk_kolegi(client, technik):
    assert client.get("/api/team/5", headers=technik).status_code == 403


def test_kierownik_widzi_raport_kazdego_technika(client, kierownik, praca):
    for technik_id in (3, 4, 5):
        assert client.get(f"/api/team/{technik_id}?{MARZEC}",
                          headers=kierownik).status_code == 200


def test_raport_technika_zawiera_jego_otwarte_zgloszenia(client, technik, praca):
    otwarte = _get(client, technik, "/api/team/3")["otwarte"]
    assert [z["id"] for z in otwarte] == [2, 304]          # od najstarszego terminu


@pytest.mark.parametrize("technik_id", [1, 999])           # pracownik, nieistniejacy
def test_raport_tylko_dla_personelu(client, kierownik, technik_id):
    assert client.get(f"/api/team/{technik_id}", headers=kierownik).status_code == 404


def test_raport_technika_waliduje_okres(client, kierownik):
    assert client.get("/api/team/3?od=2026-13-01", headers=kierownik).status_code == 400
    assert client.get("/api/team?od=abc", headers=kierownik).status_code == 400


def test_pracownik_nie_widzi_statystyk(client, pracownik):
    assert client.get("/api/team/3", headers=pracownik).status_code == 403


# ---------------------------------------------------------------
# Kolejka kierownika
# ---------------------------------------------------------------

def test_kolejka_tylko_dla_kierownika(client, technik, kierownik):
    assert client.get("/api/queue", headers=technik).status_code == 403
    assert client.get("/api/queue", headers=kierownik).status_code == 200


def test_kolejka_nieprzypisanych_i_zagrozonych(client, kierownik):
    """Zgloszenia 1 i 3 sa nowe i bez opiekuna; 1-3 sa otwarte, a ich termin
    (styczen 2026) minal. Zamkniete zgloszenie 4 nie jest w zadnej kolejce."""
    dane = _get(client, kierownik, "/api/queue")
    assert dane["nieprzypisane"]["liczba"] == 2
    assert {z["id"] for z in dane["nieprzypisane"]["zgloszenia"]} == {1, 3}
    assert dane["zagrozone"]["liczba"] == 3
    assert {z["id"] for z in dane["zagrozone"]["zgloszenia"]} == {1, 2, 3}


def test_przydzielone_zgloszenie_znika_z_kolejki(client, kierownik):
    client.patch("/api/tickets/1", headers=kierownik, json={"assigned_to": 3})
    dane = _get(client, kierownik, "/api/queue")
    assert [z["id"] for z in dane["nieprzypisane"]["zgloszenia"]] == [3]


# ---------------------------------------------------------------
# Ustawienia SLA
# ---------------------------------------------------------------

def test_technik_widzi_czasy_sla(client, technik):
    dane = _get(client, technik, "/api/settings/sla")
    assert dane["godziny"] == {"Krytyczny": 1, "Wysoki": 4, "Sredni": 8, "Niski": 24}
    assert dane["historia"] == []


def test_pracownik_nie_widzi_ustawien(client, pracownik):
    assert client.get("/api/settings/sla", headers=pracownik).status_code == 403


def test_tylko_kierownik_zmienia_sla(client, technik):
    resp = client.put("/api/settings/sla", headers=technik, json={"godziny": {"Krytyczny": 2}})
    assert resp.status_code == 403


def test_kierownik_zmienia_sla_z_historia(client, kierownik):
    resp = client.put("/api/settings/sla", headers=kierownik,
                      json={"godziny": {"Krytyczny": 2, "Niski": 24}})
    assert resp.status_code == 200
    dane = resp.get_json()
    assert dane["godziny"]["Krytyczny"] == 2 and dane["domyslne"]["Krytyczny"] == 1
    # „Niski" sie nie zmienil — w historii jest tylko faktyczna zmiana.
    assert [(h["ustawienie"], h["stara"], h["nowa"], h["kto"]) for h in dane["historia"]] == [
        ("SLA Krytyczny", "1", "2", "Tomasz Adamski")]


def test_nowy_czas_sla_dotyczy_nowych_zgloszen(client, kierownik, pracownik, technik):
    przed = client.get("/api/tickets/1", headers=technik).get_json()["sla_deadline"]
    client.put("/api/settings/sla", headers=kierownik, json={"godziny": {"Krytyczny": 3}})

    nowe = client.post("/api/tickets", headers=pracownik,
                       json={"title": "Phishing", "description": "podejrzany mail, phishing"})
    t = client.get(f"/api/tickets/{nowe.get_json()['id']}", headers=technik).get_json()
    assert t["priority"] == "Krytyczny"
    roznica = (datetime.fromisoformat(t["sla_deadline"])
               - datetime.fromisoformat(t["created_at"])).total_seconds()
    assert abs(roznica - 3 * 3600) < 60
    # Termin istniejacego zgloszenia sie nie przesunal.
    assert client.get("/api/tickets/1", headers=technik).get_json()["sla_deadline"] == przed


@pytest.mark.parametrize("cialo", [
    {"godziny": {"Pilny": 2}},
    {"godziny": {"Krytyczny": 0}},
    {"godziny": {"Krytyczny": 721}},
    {"godziny": {"Krytyczny": True}},
    {"godziny": {"Krytyczny": "4"}},
    {"godziny": {"Krytyczny": 1.5}},
    {"godziny": {}},
    {"godziny": [1, 2]},
    {},
    [1],
])
def test_nieprawidlowe_czasy_sla(client, kierownik, cialo):
    resp = client.put("/api/settings/sla", headers=kierownik, json=cialo)
    assert resp.status_code == 400
    assert client.get("/api/settings/sla", headers=kierownik).get_json()["godziny"]["Krytyczny"] == 1


# ---------------------------------------------------------------
# Migracja istniejacej bazy z rola admin
# ---------------------------------------------------------------

def test_migracja_zamienia_admina_na_kierownika(tmp_path, monkeypatch):
    from app.data import database
    stara = tmp_path / "stara.db"
    conn = sqlite3.connect(stara)
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('pracownik','technik','admin')), email TEXT);
        CREATE TABLE tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            description TEXT NOT NULL, category TEXT, priority TEXT,
            status TEXT NOT NULL DEFAULT 'Nowe',
            created_by INTEGER NOT NULL REFERENCES users(id),
            assigned_to INTEGER REFERENCES users(id), ai_categorized INTEGER DEFAULT 0,
            sla_deadline TEXT, created_at TEXT, updated_at TEXT, closed_at TEXT);
        INSERT INTO users VALUES (1, 'p', 'h', 'P', 'pracownik', NULL);
        INSERT INTO users VALUES (7, 'admin', 'h', 'A', 'admin', NULL);
        DELETE FROM users WHERE id = 7;
        INSERT INTO users VALUES (2, 'admin', 'h', 'A', 'admin', NULL);
        INSERT INTO tickets (title, description, created_by, assigned_to) VALUES ('T', 'O', 1, 2);
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_module, "DB_PATH", str(stara))
    database.init_db()
    database.init_db()                     # ponowny start niczego nie psuje

    conn = sqlite3.connect(stara)
    conn.execute("PRAGMA foreign_keys = ON")
    assert conn.execute("SELECT role FROM users WHERE id = 2").fetchone()[0] == "kierownik"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(database.MIGRACJE_WERSJI)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT u.role FROM tickets t JOIN users u ON u.id = t.assigned_to"
                        ).fetchone()[0] == "kierownik"
    # Numer usunietego konta (7) nie wraca do obiegu.
    conn.execute("INSERT INTO users (username, password, name, role) VALUES ('n', 'h', 'N', 'technik')")
    assert conn.execute("SELECT MAX(id) FROM users").fetchone()[0] == 8
    conn.close()


def _stara_baza(sciezka, *dodatkowe_sql):
    conn = sqlite3.connect(sciezka)
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('pracownik','technik','admin')), email TEXT);
        CREATE TABLE tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            description TEXT NOT NULL, category TEXT, priority TEXT,
            status TEXT NOT NULL DEFAULT 'Nowe',
            created_by INTEGER NOT NULL REFERENCES users(id),
            assigned_to INTEGER REFERENCES users(id), ai_categorized INTEGER DEFAULT 0,
            sla_deadline TEXT, created_at TEXT, updated_at TEXT, closed_at TEXT);
        INSERT INTO users VALUES (1, 'p', 'h', 'P', 'pracownik', NULL);
        INSERT INTO users VALUES (2, 'admin', 'h', 'A', 'admin', NULL);
    """ + "".join(dodatkowe_sql))
    conn.commit()
    conn.close()


def test_wczesniejsze_uszkodzenie_bazy_nie_blokuje_migracji(tmp_path, monkeypatch):
    """Zgloszenie wskazujace usunietego uzytkownika (sprzed egzekwowania kluczy
    obcych) to nie wina migracji — aplikacja musi wystartowac."""
    from app.data import database
    stara = tmp_path / "uszkodzona.db"
    _stara_baza(stara, "INSERT INTO tickets (title, description, created_by) VALUES ('T','O',99);")
    monkeypatch.setattr(db_module, "DB_PATH", str(stara))
    database.init_db()

    conn = sqlite3.connect(stara)
    assert conn.execute("SELECT role FROM users WHERE id = 2").fetchone()[0] == "kierownik"
    conn.close()


def test_nieudana_migracja_nie_zostawia_bazy_w_polowie(tmp_path, monkeypatch):
    """Blad w trakcie przebudowy wycofuje cala zmiane — stara tabela zostaje."""
    from app.data import database
    stara = tmp_path / "stara.db"
    _stara_baza(stara)
    monkeypatch.setattr(db_module, "DB_PATH", str(stara))
    # Definicja, ktorej istniejace wiersze nie spelniaja — kopiowanie sie nie uda.
    monkeypatch.setattr(database, "KOLUMNY_USERS",
                        database.KOLUMNY_USERS.replace("'pracownik','technik','kierownik'",
                                                       "'technik'"))
    with pytest.raises(sqlite3.IntegrityError):
        database.init_db()

    conn = sqlite3.connect(stara)
    assert conn.execute("SELECT role FROM users WHERE id = 2").fetchone()[0] == "admin"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    tabele = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "users_nowa" not in tabele
    conn.close()


def test_dane_demonstracyjne_maja_kierownika_i_opiekunow_firm(tmp_path, monkeypatch):
    import io
    from contextlib import redirect_stdout
    import seed
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "demo.db"))
    with redirect_stdout(io.StringIO()):
        seed.seed()

    conn = sqlite3.connect(db_module.DB_PATH)
    kierownicy = conn.execute("SELECT username FROM users WHERE role = 'kierownik'").fetchall()
    bez_opiekuna = conn.execute(
        "SELECT COUNT(*) FROM clients c WHERE NOT EXISTS"
        " (SELECT 1 FROM technician_clients tc WHERE tc.client_id = c.id)").fetchone()[0]
    # Historia: zgloszenie obsluguje technik, ktory obsluguje firme autora.
    obce = conn.execute("""
        SELECT COUNT(*) FROM tickets t JOIN users u ON u.id = t.assigned_to
        WHERE u.role = 'technik' AND t.client_id IS NOT NULL AND t.created_at < datetime('now', '-9 days')
          AND NOT EXISTS (SELECT 1 FROM technician_clients tc
                          WHERE tc.technician_id = t.assigned_to AND tc.client_id = t.client_id)
    """).fetchone()[0]
    conn.close()
    assert kierownicy == [("t.adamski",)]
    assert bez_opiekuna == 0
    assert obce == 0


# ---------------------------------------------------------------
# Wydajnosc — zapytania statystyk korzystaja z waskich indeksow
# ---------------------------------------------------------------

def _plan_zapytan(app, wywolanie):
    """Plany wszystkich zapytan wykonanych przez funkcje warstwy danych."""
    from app.data import database
    plany = []
    with app.app_context():
        db = database.get_db()
        db.set_trace_callback(lambda sql: plany.append(sql))
        wywolanie()
        db.set_trace_callback(None)
        return [" | ".join(w[3] for w in db.execute("EXPLAIN QUERY PLAN " + sql))
                for sql in plany if sql.lstrip().upper().startswith(("SELECT", "WITH"))]


def test_statystyki_zespolu_nie_przegladaja_calej_historii(app):
    """Bez wskazanych indeksow SQLite wybieral indeks rodzaju akcji i czytal kazda
    zmiane statusu — przy 100 000 zgloszen statystyki za 30 dni trwaly 350 ms."""
    from datetime import date
    from app.data import team
    od, do = date(2026, 3, 1), date(2026, 3, 31)
    plany = " || ".join(_plan_zapytan(app, lambda: (team.rozwiazania(od, do),
                                                    team.podjecia(od, do),
                                                    team.obciazenie("2026-10-01 00:00:00"))))
    assert "idx_audit_rozwiazania_w_czasie" in plany
    assert "idx_audit_rozwiazanie" in plany
    assert "idx_audit_podjecia_w_czasie" in plany
    assert "idx_audit_akcja" not in plany
    assert "idx_tickets_otwarte" in plany


def test_otwarte_zgloszenia_technika_z_indeksu(app):
    from app.data import tickets
    plany = " || ".join(_plan_zapytan(app, lambda: tickets.otwarte_przypisane(3, 20)))
    assert "idx_tickets_opiekun_otwarte" in plany


def test_statusy_otwarte_odpowiadaja_maszynie_stanow():
    """Lista w SQL musi nadazac za maszyna stanow — nowy status otwarty
    nieobecny na liscie zniknalby z kolejki kierownika."""
    from app.data.tickets import STATUSY_OTWARTE
    from app.domain.tickets import TRANSITIONS
    assert set(STATUSY_OTWARTE) == set(TRANSITIONS) - {"Rozwiazane", "Zamkniete"}
