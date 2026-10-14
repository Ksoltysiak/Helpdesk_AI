"""Testy powiadomień — kto je dostaje, czego nie widzi i jak się je czyta.

Dane testowe (conftest): pracownik k.nowak (id 1) jest autorem #1 i #2,
p.wisniewski (id 2) — #3 i #4. Technik ma id 3, administrator id 4.
"""

import pytest

from app.domain import powiadomienia as reguly

from conftest import _naglowek_dla

pytestmark = pytest.mark.integration


@pytest.fixture
def admin(client):
    return _naglowek_dla(4)


def powiadomienia(client, naglowek, **parametry):
    return client.get("/api/notifications", headers=naglowek,
                      query_string=parametry).get_json()


# ---------------------------------------------------------------
# Reguły (czyste funkcje)
# ---------------------------------------------------------------

ZGLOSZENIE = {"id": 7, "title": "Nie dziala\nVPN", "created_by": 1,
              "assigned_to": None, "priority": "Sredni"}


@pytest.mark.unit
def test_opis_zgloszenia_jest_w_jednej_linii_i_przyciety():
    assert reguly.opis_zgloszenia(7, "Nie dziala\r\n  VPN") == "#7 „Nie dziala VPN”"
    opis = reguly.opis_zgloszenia(7, "x" * 200)
    assert len(opis) < 100 and opis.endswith("…”")


@pytest.mark.unit
def test_nikt_nie_dostaje_powiadomienia_o_wlasnej_czynnosci():
    assert reguly.po_zmianie_statusu(ZGLOSZENIE, "W trakcie", wykonawca_id=1) == []
    assert reguly.po_notatce(ZGLOSZENIE, wewnetrzna=False, autor_notatki_id=1) == []
    assert reguly.po_przypisaniu(ZGLOSZENIE, nowy_opiekun_id=3, wykonawca_id=3) == []


@pytest.mark.unit
def test_przypisanie_do_obecnego_opiekuna_nie_powiadamia():
    assert reguly.po_przypisaniu({**ZGLOSZENIE, "assigned_to": 3}, 3, wykonawca_id=4) == []


@pytest.mark.unit
def test_tresc_uzywa_polskich_nazw_statusu_i_priorytetu():
    [p] = reguly.po_zmianie_statusu(ZGLOSZENIE, "Rozwiazane", wykonawca_id=3)
    assert p["tresc"].endswith("Rozwiązane")
    [p] = reguly.po_przypisaniu(ZGLOSZENIE, 3, wykonawca_id=4)
    assert "Średni" in p["tresc"]


@pytest.mark.unit
@pytest.mark.parametrize("priorytet", ["Wysoki", "Sredni", "Niski"])
def test_tylko_zgloszenie_krytyczne_trafia_do_calego_personelu(priorytet):
    assert reguly.po_utworzeniu(1, "x", priorytet, [3, 4]) == []
    assert [p["user_id"] for p in reguly.po_utworzeniu(1, "x", "Krytyczny", [3, 4])] == [3, 4]


# ---------------------------------------------------------------
# Zdarzenia w API tworzą powiadomienia
# ---------------------------------------------------------------

def test_zmiana_statusu_powiadamia_zglaszajacego(client, technik, pracownik):
    client.patch("/api/tickets/1", headers=technik, json={"status": "W trakcie"})
    dane = powiadomienia(client, pracownik)
    assert dane["nieprzeczytane"] == 1
    [p] = dane["powiadomienia"]
    assert p["ticket_id"] == 1 and p["typ"] == "status" and not p["przeczytane"]
    assert "W trakcie" in p["tresc"]


def test_pracownik_nie_dostaje_powiadomien_o_cudzych_zgloszeniach(client, technik, pracownik2):
    client.patch("/api/tickets/1", headers=technik, json={"status": "W trakcie"})
    assert powiadomienia(client, pracownik2)["nieprzeczytane"] == 0


def test_notatka_wewnetrzna_nie_powiadamia_zglaszajacego(client, technik, pracownik):
    client.post("/api/tickets/1/notes", headers=technik, json={"content": "Diagnoza"})
    assert powiadomienia(client, pracownik)["nieprzeczytane"] == 0


def test_notatka_jawna_powiadamia_zglaszajacego(client, technik, pracownik):
    client.post("/api/tickets/1/notes", headers=technik,
                json={"content": "Prosze zrestartowac komputer", "internal": False})
    [p] = powiadomienia(client, pracownik)["powiadomienia"]
    assert p["typ"] == "notatka"
    # Treść notatki zostaje w zgłoszeniu — powiadomienie tylko o niej informuje.
    assert "zrestartowac" not in p["tresc"]


def test_notatka_do_nieistniejacego_zgloszenia_nadal_zwraca_404(client, technik):
    r = client.post("/api/tickets/999/notes", headers=technik, json={"content": "x"})
    assert r.status_code == 404


def test_przypisanie_powiadamia_nowego_opiekuna(client, technik, admin):
    client.patch("/api/tickets/3", headers=admin, json={"assigned_to": 3})
    [p] = powiadomienia(client, technik)["powiadomienia"]
    assert p["typ"] == "przypisanie" and p["ticket_id"] == 3
    assert powiadomienia(client, admin)["nieprzeczytane"] == 0


def test_zgloszenie_krytyczne_powiadamia_personel(client, pracownik, technik, admin):
    r = client.post("/api/tickets", headers=pracownik, json={
        "title": "Phishing", "description": "Podejrzany e-mail z prosba o haslo, phishing"})
    assert r.get_json()["kategoryzacja_ai"]["priorytet"] == "Krytyczny"
    for naglowek in (technik, admin):
        [p] = powiadomienia(client, naglowek)["powiadomienia"]
        assert p["typ"] == "nowe_krytyczne" and p["ticket_id"] == r.get_json()["id"]
    assert powiadomienia(client, pracownik)["nieprzeczytane"] == 0


def test_zwykle_zgloszenie_nie_powiadamia_personelu(client, pracownik, technik):
    client.post("/api/tickets", headers=pracownik,
                json={"title": "Drukarka", "description": "Drukarka drukuje wolno"})
    assert powiadomienia(client, technik)["nieprzeczytane"] == 0


# ---------------------------------------------------------------
# Lista i oznaczanie
# ---------------------------------------------------------------

def test_lista_wymaga_logowania(client):
    assert client.get("/api/notifications").status_code == 401
    assert client.post("/api/notifications/read").status_code == 401


def _trzy_zmiany(client, technik):
    for status in ("W trakcie", "Wstrzymane", "W trakcie"):
        client.patch("/api/tickets/1", headers=technik, json={"status": status})


def test_lista_od_najnowszego_z_limitem(client, technik, pracownik):
    _trzy_zmiany(client, technik)
    dane = powiadomienia(client, pracownik, limit=2)
    assert dane["nieprzeczytane"] == 3
    ids = [p["id"] for p in dane["powiadomienia"]]
    assert len(ids) == 2 and ids == sorted(ids, reverse=True)


def test_oznaczenie_wybranych(client, technik, pracownik):
    _trzy_zmiany(client, technik)
    najnowsze = powiadomienia(client, pracownik)["powiadomienia"][0]["id"]
    r = client.post("/api/notifications/read", headers=pracownik, json={"ids": [najnowsze]})
    assert r.get_json() == {"oznaczono": 1, "nieprzeczytane": 2}
    assert powiadomienia(client, pracownik)["powiadomienia"][0]["przeczytane"]


def test_oznaczenie_wszystkich_bez_ciala_zadania(client, technik, pracownik):
    _trzy_zmiany(client, technik)
    r = client.post("/api/notifications/read", headers=pracownik)
    assert r.get_json() == {"oznaczono": 3, "nieprzeczytane": 0}
    # Ponowne oznaczenie niczego nie zmienia.
    assert client.post("/api/notifications/read", headers=pracownik).get_json()["oznaczono"] == 0


def test_pusta_lista_ids_niczego_nie_oznacza(client, technik, pracownik):
    _trzy_zmiany(client, technik)
    r = client.post("/api/notifications/read", headers=pracownik, json={"ids": []})
    assert r.get_json() == {"oznaczono": 0, "nieprzeczytane": 3}


def test_nie_da_sie_oznaczyc_cudzych_powiadomien(client, technik, pracownik, pracownik2):
    _trzy_zmiany(client, technik)
    cudze = [p["id"] for p in powiadomienia(client, pracownik)["powiadomienia"]]
    r = client.post("/api/notifications/read", headers=pracownik2, json={"ids": cudze})
    assert r.get_json()["oznaczono"] == 0
    assert powiadomienia(client, pracownik)["nieprzeczytane"] == 3


@pytest.mark.parametrize("ids", ["1", [True], ["1"], [1.5], {"a": 1}, list(range(101))])
def test_nieprawidlowe_ids_to_400(client, pracownik, ids):
    r = client.post("/api/notifications/read", headers=pracownik, json={"ids": ids})
    assert r.status_code == 400
