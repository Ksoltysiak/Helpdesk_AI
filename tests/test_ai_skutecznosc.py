"""Testy jakości kategoryzacji: normalizacja polskich znaków, pewność
decyzji, eskalacja priorytetu oraz skuteczność na zbiorze ewaluacyjnym.

Zbiór ewaluacyjny (`zbior_ewaluacyjny.py`) pełni tu rolę progu jakości:
pogorszenie skuteczności zatrzyma budowanie, tak samo jak zwykły błąd.
"""

import pytest

from app.domain.ai import categorize, PROG_PEWNOSCI, _bez_diakrytykow
from zbior_ewaluacyjny import ZBIOR, NIEROZPOZNAWALNE

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------
# REGRESJA: slownik bez diakrytykow nie trafial w polszczyzne
#
# Slowa kluczowe zapisane sa bez polskich znakow („haslo"), a uzytkownicy
# pisza z nimi („hasło"). Bez normalizacji tekstu wejsciowego zgloszenie
# „Zapomniane hasło" nie dopasowywalo sie do niczego i po cichu wpadalo
# do kategorii domyslnej.
# ---------------------------------------------------------------

@pytest.mark.parametrize("z_polskimi,bez_polskich", [
    ("hasło", "haslo"),
    ("sieć", "siec"),
    ("sprzęt", "sprzet"),
    ("uprawnień", "uprawnien"),
    ("załącznik", "zalacznik"),
    ("wyłudzenie", "wyludzenie"),
    ("ŻÓŁĆ", "ZOLC"),
])
def test_normalizacja_sprowadza_polskie_znaki(z_polskimi, bez_polskich):
    assert _bez_diakrytykow(z_polskimi) == bez_polskich


@pytest.mark.parametrize("tytul,opis,kategoria", [
    ("Zapomniane hasło", "Proszę o reset hasła do komputera", "Konta i dostep"),
    ("Brak uprawnień", "Nie mam uprawnień do katalogu", "Konta i dostep"),
    ("Awaria sieci", "Cała sieć nie odpowiada", "Siec"),
    ("Zepsuty sprzęt", "Sprzęt komputerowy nie działa", "Sprzet"),
    ("Próba wyłudzenia", "Ktoś próbował wyłudzić moje hasło", "Bezpieczenstwo"),
])
def test_poprawna_polszczyzna_jest_rozpoznawana(tytul, opis, kategoria):
    assert categorize(tytul, opis)["kategoria"] == kategoria


def test_pisownia_z_polskimi_znakami_i_bez_daje_ten_sam_wynik():
    z_pl = categorize("Zapomniane hasło", "Nie pamiętam hasła")
    bez_pl = categorize("Zapomniane haslo", "Nie pamietam hasla")
    assert z_pl["kategoria"] == bez_pl["kategoria"]
    assert z_pl["priorytet"] == bez_pl["priorytet"]


# ---------------------------------------------------------------
# Pewność decyzji
# ---------------------------------------------------------------

def test_pewnosc_jest_w_zakresie_0_1():
    for tytul, opis, _k, _p in ZBIOR:
        pewnosc = categorize(tytul, opis)["pewnosc"]
        assert 0.0 <= pewnosc <= 1.0


def test_jednoznaczne_zgloszenie_ma_wysoka_pewnosc():
    wynik = categorize("Drukarka nie drukuje", "Drukarka w sekretariacie nie przyjmuje zleceń")
    assert wynik["pewnosc"] >= PROG_PEWNOSCI
    assert wynik["wymaga_weryfikacji"] is False


@pytest.mark.parametrize("tytul,opis", NIEROZPOZNAWALNE)
def test_zgloszenie_spoza_domeny_it_jest_oznaczane_do_weryfikacji(tytul, opis):
    """Modul ma powiedziec 'nie wiem' zamiast zgadywac kategorie."""
    wynik = categorize(tytul, opis)
    assert wynik["pewnosc"] == 0.0
    assert wynik["wymaga_weryfikacji"] is True


def test_uzasadnienie_wskazuje_slowa_ktore_zadecydowaly():
    """Technik musi widziec, DLACZEGO modul tak zaklasyfikowal zgloszenie."""
    wynik = categorize("Nie działa VPN", "Błąd połączenia z siecią firmową")
    assert "vpn" in wynik["dopasowania"]
    assert all(isinstance(s, str) for s in wynik["dopasowania"])


def test_wiecej_przeslanek_to_wieksza_pewnosc():
    jedno = categorize("Problem z Outlookiem", "")
    wiele = categorize("Problem z Outlookiem", "poczta i skrzynka nie działają")
    assert wiele["pewnosc"] > jedno["pewnosc"]


# ---------------------------------------------------------------
# Eskalacja priorytetu
# ---------------------------------------------------------------

def test_skala_awarii_podnosi_priorytet():
    jedna_osoba = categorize("Brak internetu", "Nie mam dostępu do internetu")
    caly_dzial = categorize("Brak internetu", "Cały dział nie ma dostępu do internetu")
    from app.domain.ai import _RANGA
    assert _RANGA[caly_dzial["priorytet"]] > _RANGA[jedna_osoba["priorytet"]]


def test_pilnosc_podnosi_priorytet():
    zwykle = categorize("Problem z laptopem", "Laptop działa wolno")
    pilne = categorize("Problem z laptopem", "Laptop w ogóle nie włącza się, pilne")
    from app.domain.ai import _RANGA
    assert _RANGA[pilne["priorytet"]] > _RANGA[zwykle["priorytet"]]


def test_zwrot_nie_dziala_sam_w_sobie_nie_eskaluje():
    """„Nie działa" to domyślny opis usterki po polsku — gdyby podnosił
    priorytet, prawie każde zgłoszenie byłoby pilne i priorytety przestałyby
    cokolwiek rozróżniać."""
    assert categorize("Myszka nie działa", "Myszka nie działa")["priorytet"] == "Niski"
    assert categorize("Drukarka nie działa", "Nie drukuje")["priorytet"] == "Niski"


def test_bezpieczenstwo_zawsze_krytyczne_mimo_lagodnego_opisu():
    """Incydentu bezpieczenstwa nie wolno zaniżyć — koszt pomyłki jest zbyt duży."""
    wynik = categorize("Drobna sprawa", "Chyba nic wielkiego, ale dostałem phishing")
    assert wynik["kategoria"] == "Bezpieczenstwo"
    assert wynik["priorytet"] == "Krytyczny"


# ---------------------------------------------------------------
# Skuteczność na zbiorze ewaluacyjnym — próg jakości
# ---------------------------------------------------------------

def _skutecznosc():
    kat = pri = 0
    for tytul, opis, kategoria, priorytety in ZBIOR:
        w = categorize(tytul, opis)
        kat += w["kategoria"] == kategoria
        pri += w["priorytet"] in priorytety
    return kat / len(ZBIOR), pri / len(ZBIOR)


def test_skutecznosc_kategorii_nie_spada_ponizej_progu():
    """Przed przebudową moduł osiągał 79%. Próg 90% pilnuje, by zmiany
    w słowniku nie cofnęły tej poprawy."""
    kategoria, _ = _skutecznosc()
    assert kategoria >= 0.90, f"Skutecznosc kategorii spadla do {kategoria:.1%}"


def test_skutecznosc_priorytetu_nie_spada_ponizej_progu():
    _, priorytet = _skutecznosc()
    assert priorytet >= 0.90, f"Skutecznosc priorytetu spadla do {priorytet:.1%}"


def test_zaden_incydent_bezpieczenstwa_nie_jest_przeoczony():
    """Najwazniejszy pojedynczy wymog: zgloszenie bezpieczenstwa musi trafic
    do wlasciwej kategorii z priorytetem krytycznym i SLA 1h."""
    incydenty = [(t, o) for t, o, k, _p in ZBIOR if k == "Bezpieczenstwo"]
    assert incydenty, "Zbior ewaluacyjny musi zawierac incydenty bezpieczenstwa"
    for tytul, opis in incydenty:
        w = categorize(tytul, opis)
        assert w["kategoria"] == "Bezpieczenstwo", f"Przeoczony incydent: {tytul}"
        assert w["priorytet"] == "Krytyczny", f"Zanizony priorytet: {tytul}"
