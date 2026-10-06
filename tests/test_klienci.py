"""Testy klientow — firm, ktorych pracownicy zglaszaja awarie.

Klient jest podstawa przyszlych raportow, wiec najwazniejsze sa tu dwie
wlasnosci: kazde zgloszenie trafia do wlasciwej firmy, a pracownik jednej
firmy nie dosiega danych innych klientow.
"""

import io
import sqlite3
from contextlib import redirect_stdout

import pytest

from app import config as db_module

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------
# GET /api/clients
# ---------------------------------------------------------------

def test_lista_klientow_wymaga_zalogowania(client):
    assert client.get("/api/clients").status_code == 401


def test_pracownik_nie_widzi_listy_klientow(client, pracownik):
    """Nazwy i skala zgloszen innych firm nie sa dla pracownika."""
    assert client.get("/api/clients", headers=pracownik).status_code == 403


def test_lista_klientow_zawiera_liczniki(client, technik):
    klienci = {k["name"]: k for k in client.get("/api/clients", headers=technik).get_json()}

    a = klienci["Firma Testowa A"]    # zgloszenia 1 (Nowe) i 2 (W trakcie)
    assert (a["pracownikow"], a["zgloszen"], a["otwartych"]) == (1, 2, 2)

    b = klienci["Firma Testowa B"]    # zgloszenia 3 (Nowe) i 4 (Zamkniete)
    assert (b["pracownikow"], b["zgloszen"], b["otwartych"]) == (1, 2, 1)


def test_klient_bez_zgloszen_jest_na_liscie_z_zerami(client, technik):
    klienci = {k["name"]: k for k in client.get("/api/clients", headers=technik).get_json()}
    pusty = klienci["Firma Bez Zgloszen"]
    assert (pusty["pracownikow"], pusty["zgloszen"], pusty["otwartych"]) == (0, 0, 0)


def test_lista_klientow_jest_posortowana_alfabetycznie(client, technik):
    nazwy = [k["name"] for k in client.get("/api/clients", headers=technik).get_json()]
    assert nazwy == sorted(nazwy)


def test_nowe_zgloszenie_zwieksza_liczniki_klienta(client, pracownik, technik):
    client.post("/api/tickets", headers=pracownik,
                json={"title": "Drukarka", "description": "brak tonera"})
    klienci = {k["name"]: k for k in client.get("/api/clients", headers=technik).get_json()}
    assert klienci["Firma Testowa A"]["zgloszen"] == 3
    assert klienci["Firma Testowa A"]["otwartych"] == 3


# ---------------------------------------------------------------
# Klient w zgloszeniach
# ---------------------------------------------------------------

def test_szczegoly_zgloszenia_zawieraja_klienta(client, technik):
    dane = client.get("/api/tickets/3", headers=technik).get_json()
    assert dane["client_id"] == 2
    assert dane["client_name"] == "Firma Testowa B"


def test_nowe_zgloszenie_nalezy_do_firmy_autora(client, pracownik2, technik):
    nowe = client.post("/api/tickets", headers=pracownik2,
                       json={"title": "VPN", "description": "nie dziala vpn"}).get_json()
    dane = client.get(f"/api/tickets/{nowe['id']}", headers=technik).get_json()
    assert dane["client_name"] == "Firma Testowa B"


def test_zgloszenie_zostaje_przy_firmie_po_zmianie_pracodawcy(client, pracownik, technik, app):
    """Raport dla klienta nie moze zmieniac sie wstecz, gdy pracownik odejdzie."""
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("UPDATE users SET client_id = 2 WHERE id = 1")
    conn.commit()
    conn.close()

    assert client.get("/api/tickets/1", headers=technik).get_json()["client_id"] == 1
    nowe = client.post("/api/tickets", headers=pracownik,
                       json={"title": "Monitor", "description": "monitor migocze"}).get_json()
    assert client.get(f"/api/tickets/{nowe['id']}", headers=technik).get_json()["client_id"] == 2


# ---------------------------------------------------------------
# Filtrowanie listy po kliencie
# ---------------------------------------------------------------

def test_technik_filtruje_zgloszenia_po_kliencie(client, technik):
    dane = client.get("/api/tickets?client_id=2", headers=technik).get_json()
    assert {t["id"] for t in dane["tickets"]} == {3, 4}
    assert dane["total"] == 2


def test_filtr_klienta_laczy_sie_z_innymi_filtrami(client, technik):
    dane = client.get("/api/tickets?client_id=2&status=Nowe", headers=technik).get_json()
    assert [t["id"] for t in dane["tickets"]] == [3]


def test_filtr_klienta_nie_omija_izolacji_pracownika(client, pracownik):
    """Pracownik firmy A prosi o zgloszenia firmy B — dostaje tylko wlasne."""
    dane = client.get("/api/tickets?client_id=2", headers=pracownik).get_json()
    assert {t["id"] for t in dane["tickets"]} == {1, 2}


@pytest.mark.parametrize("wartosc", ["abc", "999", "-1", "1 OR 1=1"])
def test_nieprawidlowy_filtr_klienta_nie_powoduje_bledu(client, technik, wartosc):
    resp = client.get(f"/api/tickets?client_id={wartosc}", headers=technik)
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0


# ---------------------------------------------------------------
# Klient zalogowanej osoby
# ---------------------------------------------------------------

def test_logowanie_pracownika_zwraca_jego_firme(client):
    dane = client.post("/api/auth/login",
                       json={"username": "k.nowak", "password": "haslo123"}).get_json()
    assert dane["client_id"] == 1
    assert dane["client_name"] == "Firma Testowa A"


def test_personel_helpdesku_nie_ma_klienta(client, technik):
    dane = client.get("/api/auth/me", headers=technik).get_json()
    assert dane["client_id"] is None and dane["client_name"] is None


# ---------------------------------------------------------------
# Migracja istniejacej bazy i dane demonstracyjne
# ---------------------------------------------------------------

def test_istniejace_zgloszenia_dziedzicza_firme_autora(app):
    """Zgloszenia sprzed wprowadzenia klientow uzupelnia start aplikacji."""
    from app.data import database
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("UPDATE tickets SET client_id = NULL")
    conn.commit()
    conn.close()

    database.init_db()

    conn = sqlite3.connect(db_module.DB_PATH)
    wiersze = conn.execute(
        "SELECT t.client_id, u.client_id FROM tickets t JOIN users u ON u.id = t.created_by"
    ).fetchall()
    conn.close()
    assert wiersze and all(zgloszenie == autor for zgloszenie, autor in wiersze)


def test_uzupelnienie_nie_nadpisuje_przypisanego_klienta(app):
    """Ponowny start nie moze przepisac zgloszen do obecnej firmy autora."""
    from app.data import database
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("UPDATE users SET client_id = 2 WHERE id = 1")
    conn.commit()
    conn.close()

    database.init_db()

    conn = sqlite3.connect(db_module.DB_PATH)
    klient = conn.execute("SELECT client_id FROM tickets WHERE id = 1").fetchone()[0]
    conn.close()
    assert klient == 1


def test_dane_demonstracyjne_maja_piec_firm_z_pracownikami(tmp_path, monkeypatch):
    import seed
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "demo.db"))
    with redirect_stdout(io.StringIO()):
        seed.seed()

    conn = sqlite3.connect(db_module.DB_PATH)
    klienci = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    bez_firmy = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'pracownik' AND client_id IS NULL").fetchone()[0]
    personel_z_firma = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role != 'pracownik' AND client_id IS NOT NULL").fetchone()[0]
    firmy_bez_zgloszen = conn.execute(
        "SELECT COUNT(*) FROM clients c WHERE NOT EXISTS"
        " (SELECT 1 FROM tickets t WHERE t.client_id = c.id)").fetchone()[0]
    niezgodne = conn.execute(
        "SELECT COUNT(*) FROM tickets t JOIN users u ON u.id = t.created_by"
        " WHERE t.client_id IS NOT u.client_id").fetchone()[0]
    conn.close()

    assert klienci == 5
    assert bez_firmy == 0, "Kazdy pracownik musi nalezec do firmy"
    assert personel_z_firma == 0, "Technik i admin obsluguja wszystkie firmy"
    assert firmy_bez_zgloszen == 0, "Kazda firma demonstracyjna ma zgloszenia do raportu"
    assert niezgodne == 0
