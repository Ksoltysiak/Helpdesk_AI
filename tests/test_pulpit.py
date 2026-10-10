"""Testy pulpitu „na żywo" — puls kolejki, SLA, aktywność, obciążenie zespołu.

Dane testowe (conftest): wszystkie terminy SLA minęły (2026-01-01), aktywne
są zgłoszenia #1, #2 i #3, technik (id 3) obsługuje tylko #2, a #4 jest
zamknięte. Najważniejsze tu jest to, żeby pulpit liczył to samo co lista
po kliknięciu w kafelek, i żeby pracownik nie dostał obrazu pracy helpdesku.
"""

import pytest

from app.api.meta import DNI_TRENDU

pytestmark = pytest.mark.integration


def pulpit(client, naglowek):
    return client.get("/api/dashboard", headers=naglowek).get_json()


def liczba(client, naglowek, filtr):
    return client.get(f"/api/tickets?{filtr}", headers=naglowek).get_json()["total"]


# ---------------------------------------------------------------
# Puls kolejki
# ---------------------------------------------------------------

def test_puls_liczy_kolejke(client, technik):
    p = pulpit(client, technik)["puls"]
    assert p["po_terminie"] == 3      # wszystkie aktywne mają termin w przeszłości
    assert p["zagrozone"] == 0        # po terminie to nie „zagrożone"
    assert p["nieprzypisane"] == 2    # #1 i #3; zamknięte się nie liczy
    assert p["moje"] == 1             # #2


def test_zgloszenie_utworzone_dzis_trafia_do_licznika_dnia(client, technik, pracownik):
    przed = pulpit(client, technik)["puls"]["dzis_nowe"]
    client.post("/api/tickets", headers=pracownik,
                json={"title": "Nie dziala VPN", "description": "Brak polaczenia z VPN"})
    assert pulpit(client, technik)["puls"]["dzis_nowe"] == przed + 1


def test_nowe_zgloszenie_jest_zagrozone_a_nie_po_terminie(client, technik, pracownik):
    """Krytyczne ma SLA 1 h — od razu mieści się w oknie zagrożenia (2 h)."""
    client.post("/api/tickets", headers=pracownik,
                json={"title": "Phishing", "description": "Podejrzany e-mail z prosba o haslo, phishing"})
    p = pulpit(client, technik)["puls"]
    assert p["zagrozone"] == 1
    assert p["po_terminie"] == 3


@pytest.mark.parametrize("klucz,filtr", [
    ("po_terminie",   "sla=przekroczone"),
    ("nieprzypisane", "przypisane=brak&aktywne=1"),
    ("moje",          "przypisane=ja&aktywne=1"),
])
def test_kafelek_zgadza_sie_z_lista_po_kliknieciu(client, technik, klucz, filtr):
    assert pulpit(client, technik)["puls"][klucz] == liczba(client, technik, filtr)


# ---------------------------------------------------------------
# Wykresy i listy
# ---------------------------------------------------------------

def test_trend_ma_kazdy_dzien_okresu(client, technik):
    trend = pulpit(client, technik)["trend"]
    assert len(trend) == DNI_TRENDU
    assert [d["data"] for d in trend] == sorted(d["data"] for d in trend)
    # Dane testowe powstały dziś (domyślny created_at) — reszta dni to zera.
    assert trend[-1]["nowe"] == 4
    assert sum(d["nowe"] for d in trend[:-1]) == 0


def test_priorytety_tylko_aktywnych(client, technik):
    assert pulpit(client, technik)["wg_priorytetu"] == {"Krytyczny": 1, "Sredni": 1, "Niski": 1}


def test_pilne_sla_od_najbardziej_spoznionego(client, technik):
    pilne = pulpit(client, technik)["pilne_sla"]
    assert {t["id"] for t in pilne} == {1, 2, 3}
    assert all(t["sla_deadline"].endswith("Z") for t in pilne)


def test_obciazenie_obejmuje_caly_personel(client, technik):
    """Także osoby bez zgłoszeń — inaczej nie widać, kto ma wolne ręce."""
    osoby = {o["name"]: o for o in pulpit(client, technik)["obciazenie"]}
    assert osoby["Marek Lewandowski"]["aktywne"] == 1
    assert osoby["Tomasz Adamski"]["aktywne"] == 0
    assert "Katarzyna Nowak" not in osoby          # pracownik to nie personel


# ---------------------------------------------------------------
# Kanał aktywności
# ---------------------------------------------------------------

def test_aktywnosc_pokazuje_najnowsze_zdarzenia(client, technik, pracownik):
    nowe = client.post("/api/tickets", headers=pracownik,
                       json={"title": "Drukarka", "description": "Drukarka nie drukuje"}).get_json()
    akcje = {(a["ticket_id"], a["action"]) for a in pulpit(client, technik)["aktywnosc"]}
    assert (nowe["id"], "Utworzenie") in akcje
    assert (nowe["id"], "Kategoryzacja AI") in akcje


def test_pracownik_nie_widzi_notatek_ani_cudzych_zgloszen(client, technik, pracownik, pracownik2):
    client.post("/api/tickets/1/notes", headers=technik, json={"content": "Tajna diagnoza"})
    client.post("/api/tickets", headers=pracownik2,
                json={"title": "Cudze", "description": "Zgloszenie innej firmy"})
    wlasne = client.post("/api/tickets", headers=pracownik,
                         json={"title": "Moje", "description": "Nie dziala VPN"}).get_json()

    wpisy = pulpit(client, pracownik)["aktywnosc"]
    assert {a["ticket_id"] for a in wpisy} == {wlasne["id"]}
    assert {a["action"] for a in wpisy} == {"Utworzenie"}
    assert all("Tajna" not in (a["new"] or "") for a in wpisy)


# ---------------------------------------------------------------
# Granica dostępu
# ---------------------------------------------------------------

def test_pracownik_nie_dostaje_obrazu_pracy_helpdesku(client, pracownik):
    dane = pulpit(client, pracownik)
    for klucz in ("puls", "trend", "wg_priorytetu", "pilne_sla", "obciazenie"):
        assert klucz not in dane


def test_filtr_aktywnych_dziala_tez_dla_pracownika(client, pracownik):
    assert liczba(client, pracownik, "aktywne=1") == 2


def test_skroty_technika_nie_omijaja_izolacji_pracownika(client, pracownik):
    """`przypisane` i `sla` są tylko dla personelu — pracownik widzi swoje i tyle."""
    for filtr in ("przypisane=brak", "sla=przekroczone", "przypisane=ja"):
        dane = client.get(f"/api/tickets?{filtr}", headers=pracownik).get_json()
        assert {t["created_by"] for t in dane["tickets"]} == {1}
        assert dane["total"] == 2


@pytest.mark.parametrize("filtr,oczekiwane", [
    ("aktywne=1", 3),
    ("przypisane=brak", 2),
    ("przypisane=nieznane", 4),     # nieznana wartość skrótu nie zawęża listy
    ("aktywne=1&priority=Krytyczny", 1),
])
def test_skroty_listy_technika(client, technik, filtr, oczekiwane):
    assert liczba(client, technik, filtr) == oczekiwane
