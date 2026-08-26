"""Testy jednostkowe maszyny stanow zgloszenia (routes.TRANSITIONS).

Sama tabela przejsc, bez uruchamiania API — testy integracyjne sprawdzaja
osobno, czy endpoint faktycznie tej tabeli przestrzega.
"""

import pytest

from app.domain.tickets import TRANSITIONS

pytestmark = pytest.mark.unit

STATUSY = set(TRANSITIONS)


def test_kazdy_status_docelowy_jest_znanym_statusem():
    for status, dozwolone in TRANSITIONS.items():
        for cel in dozwolone:
            assert cel in STATUSY, f"'{status}' -> '{cel}' wskazuje nieznany status"


def test_zamkniete_jest_stanem_koncowym():
    assert TRANSITIONS["Zamkniete"] == []


def test_zaden_status_nie_przechodzi_sam_w_siebie():
    for status, dozwolone in TRANSITIONS.items():
        assert status not in dozwolone


def test_nie_da_sie_przeskoczyc_z_nowe_do_zamkniete():
    """Zgloszenie musi przejsc przez obsluge — to regula biznesowa, nie detal."""
    assert "Zamkniete" not in TRANSITIONS["Nowe"]


def test_nowe_zgloszenie_mozna_wylacznie_podjac():
    assert TRANSITIONS["Nowe"] == ["W trakcie"]


def test_kazdy_status_poza_koncowym_ma_wyjscie():
    for status, dozwolone in TRANSITIONS.items():
        if status != "Zamkniete":
            assert dozwolone, f"'{status}' nie ma zadnego przejscia — zgloszenie utknie"


def test_wstrzymane_wraca_do_obslugi():
    assert "W trakcie" in TRANSITIONS["Wstrzymane"]


def test_rozwiazane_mozna_cofnac_do_obslugi():
    """Technik musi miec mozliwosc wznowienia zle rozwiazanego zgloszenia."""
    assert "W trakcie" in TRANSITIONS["Rozwiazane"]


def test_kazdy_status_jest_osiagalny_z_nowe():
    osiagalne, kolejka = {"Nowe"}, ["Nowe"]
    while kolejka:
        for cel in TRANSITIONS[kolejka.pop()]:
            if cel not in osiagalne:
                osiagalne.add(cel)
                kolejka.append(cel)
    assert osiagalne == STATUSY
