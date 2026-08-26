"""Testy jednostkowe modulu kategoryzacji AI (ai.py).

Czysta funkcja, bez I/O — najszybsza i najliczniejsza warstwa piramidy.
"""

import pytest

from app.domain.ai import categorize, CATEGORIES, KEYWORDS, SLA_HOURS

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------
# Podstawowy kontrakt funkcji
# ---------------------------------------------------------------

def test_zwraca_komplet_pol():
    """Poza decyzja moduł zwraca tez jej pewnosc i uzasadnienie."""
    result = categorize("Nie dziala VPN", "Blad TLS handshake")
    assert set(result) == {"kategoria", "priorytet", "pewnosc",
                           "wymaga_weryfikacji", "dopasowania"}


def test_kategoria_zawsze_z_dozwolonej_listy():
    result = categorize("Nie dziala VPN", "Blad TLS")
    assert result["kategoria"] in CATEGORIES


def test_priorytet_zawsze_ma_zdefiniowane_sla():
    result = categorize("Nie dziala VPN", "Blad TLS")
    assert result["priorytet"] in SLA_HOURS


def test_brak_dopasowania_konczy_sie_przyznaniem_do_niewiedzy():
    """Zamiast po cichu zgadywac, moduł ma zasygnalizowac brak przeslanek."""
    result = categorize("Cos dziwnego", "Nieokreslony problem bez slow kluczowych")
    assert result["pewnosc"] == 0.0
    assert result["wymaga_weryfikacji"] is True
    assert result["dopasowania"] == []


def test_dopasowanie_ignoruje_wielkosc_liter():
    assert categorize("PHISHING", "")["kategoria"] == "Bezpieczenstwo"
    assert categorize("phishing", "")["kategoria"] == "Bezpieczenstwo"


def test_uwzglednia_zarowno_tytul_jak_i_opis():
    z_tytulu = categorize("phishing", "brak innych slow")
    z_opisu = categorize("brak innych slow", "phishing")
    assert z_tytulu["kategoria"] == z_opisu["kategoria"] == "Bezpieczenstwo"


# ---------------------------------------------------------------
# REGRESJA: incydenty bezpieczenstwa byly zaniżane w priorytecie
#
# Poprzednia implementacja zwracala PIERWSZE dopasowane slowo kluczowe.
# Poniewaz "haslo" i "komputer" wystepuja w slowniku przed "phishing"
# i "wirus", zgloszenie phishingowe trafialo do kategorii "Konta i dostep"
# z priorytetem "Sredni" (SLA 8h) zamiast "Bezpieczenstwo"/"Krytyczny"
# (SLA 1h).
# ---------------------------------------------------------------

@pytest.mark.parametrize("tytul,opis", [
    ("Phishing w skrzynce", "Dostalem podejrzany mail z prosba o haslo do konta"),
    ("Podejrzany e-mail", "Prosba o podanie hasla, wyglada na phishing"),
    ("Wirus na komputerze", "Antywirus wykryl malware na moim komputerze"),
    ("Ransomware", "Pliki zaszyfrowane, zadanie okupu, konto zablokowane"),
])
def test_incydent_bezpieczenstwa_ma_najwyzszy_priorytet(tytul, opis):
    """Slowo o wyzszej wadze musi wygrac z lagodniejszym slowem w tym samym tekscie."""
    result = categorize(tytul, opis)
    assert result["kategoria"] == "Bezpieczenstwo"
    assert result["priorytet"] == "Krytyczny"
    assert SLA_HOURS[result["priorytet"]] == 1


def test_dowody_z_wielu_slow_sa_sumowane():
    """Dwa slowa tej samej kategorii daja wyzsza pewnosc niz jedno."""
    jedno = categorize("Problem z drukarka", "")
    dwa = categorize("Problem z drukarka", "skaner tez nie odpowiada")
    assert dwa["pewnosc"] >= jedno["pewnosc"]
    assert len(dwa["dopasowania"]) > len(jedno["dopasowania"])


# ---------------------------------------------------------------
# Brak przesadnego podnoszenia priorytetu (druga strona medalu)
# ---------------------------------------------------------------

@pytest.mark.parametrize("tytul,opis,oczekiwany", [
    ("Wymiana klawiatury", "Kilka klawiszy nie dziala", "Niski"),
    ("Zapomniane haslo", "Nie pamietam hasla do skrzynki", "Sredni"),
    ("Nie dziala VPN", "Blad TLS handshake", "Wysoki"),
])
def test_zwykle_zgloszenia_nie_sa_eskalowane(tytul, opis, oczekiwany):
    assert categorize(tytul, opis)["priorytet"] == oczekiwany


# ---------------------------------------------------------------
# Niezmienniki slownika slow kluczowych
# ---------------------------------------------------------------

def test_kazde_slowo_kluczowe_wskazuje_istniejaca_kategorie():
    for keyword, (category, _, _w) in KEYWORDS.items():
        assert category in CATEGORIES, f"'{keyword}' wskazuje nieznana kategorie '{category}'"


def test_kazde_slowo_kluczowe_ma_priorytet_ze_zdefiniowanym_sla():
    for keyword, (_, priority, _w) in KEYWORDS.items():
        assert priority in SLA_HOURS, f"'{keyword}' ma priorytet '{priority}' bez SLA"


def test_kazde_slowo_kluczowe_ma_sensowna_wage():
    for keyword, (_, _p, waga) in KEYWORDS.items():
        assert isinstance(waga, int) and 1 <= waga <= 3, f"'{keyword}' ma wage {waga}"


POLSKIE_ZNAKI = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"


def test_slownik_jest_zapisany_bez_polskich_znakow():
    """Tekst wejsciowy jest normalizowany, wiec slownik musi byc w tej samej postaci.

    Rdzen zawierajacy polski znak nie dopasowalby sie nigdy — to wlasnie ta
    niezgodnosc powodowala, ze modul nie rozpoznawal poprawnej polszczyzny.
    """
    with_diakrytykami = [k for k in KEYWORDS if any(z in k for z in POLSKIE_ZNAKI)]
    assert not with_diakrytykami, f"Rdzenie nie do dopasowania: {with_diakrytykami}"


def test_sla_rosnie_wraz_ze_spadkiem_pilnosci():
    assert SLA_HOURS["Krytyczny"] < SLA_HOURS["Wysoki"] < SLA_HOURS["Sredni"] < SLA_HOURS["Niski"]
