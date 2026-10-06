"""Testy jednostkowe regul raportow — bez bazy i bez HTTP."""

from datetime import date

import pytest

from app.domain import reports as r

pytestmark = pytest.mark.unit

DZIS = date(2026, 10, 6)


# ---------------------------------------------------------------
# Okres
# ---------------------------------------------------------------

def test_bez_dat_ostatnie_30_dni():
    assert r.okres(None, None, DZIS) == (date(2026, 9, 7), DZIS)


def test_sama_data_od_oznacza_do_dzis():
    assert r.okres("2026-09-01", None, DZIS) == (date(2026, 9, 1), DZIS)


def test_sama_data_od_sprzed_ponad_roku_jest_odrzucana():
    """„Od 2024 do dziś" przekracza limit — klient dostaje czytelny błąd."""
    with pytest.raises(r.BladOkresu, match="366"):
        r.okres("2024-01-01", None, DZIS)


def test_sama_data_do_daje_30_dni_wstecz():
    assert r.okres(None, "2026-01-30", DZIS) == (date(2026, 1, 1), date(2026, 1, 30))


def test_jednodniowy_okres_jest_dozwolony():
    assert r.okres("2026-03-05", "2026-03-05", DZIS) == (date(2026, 3, 5), date(2026, 3, 5))


@pytest.mark.parametrize("od,do", [
    (123, None), ("2026-03-05 ", None), (" 2026-03-05", None), ("2026/03/05", None),
])
def test_nieprawidlowy_zapis_daty(od, do):
    with pytest.raises(r.BladOkresu):
        r.okres(od, do, DZIS)


def test_okres_poprzedni_przez_przelom_roku():
    assert r.poprzedni_okres(date(2026, 1, 1), date(2026, 1, 31)) == (
        date(2025, 12, 1), date(2025, 12, 31))


def test_okres_poprzedni_w_roku_przestepnym():
    """Marzec 2024 (31 dni) — poprzedni okres zaczyna sie 30 stycznia."""
    assert r.poprzedni_okres(date(2024, 3, 1), date(2024, 3, 31)) == (
        date(2024, 1, 30), date(2024, 2, 29))


def test_najwczesniejsza_dozwolona_data_nie_przepelnia_okresu_poprzedniego():
    od, do = r.okres("2000-01-01", "2000-12-31", DZIS)     # 366 dni — rok przestepny
    assert r.poprzedni_okres(od, do) == (date(1998, 12, 31), date(1999, 12, 31))


# ---------------------------------------------------------------
# Grupowanie i trend
# ---------------------------------------------------------------

@pytest.mark.parametrize("dni,oczekiwane", [
    (1, "dzien"), (31, "dzien"), (32, "tydzien"), (183, "tydzien"), (184, "miesiac"),
    (366, "miesiac"),
])
def test_progi_grupowania(dni, oczekiwane):
    from datetime import timedelta
    od = date(2025, 1, 1)
    assert r.grupowanie(od, od + timedelta(days=dni - 1)) == oczekiwane


def test_trend_miesieczny_przez_przelom_roku():
    od, do = date(2025, 9, 15), date(2026, 3, 31)          # 198 dni
    dziennie = {date(2025, 9, 15): 2, date(2025, 12, 31): 1, date(2026, 1, 1): 4,
                date(2026, 3, 31): 1}
    trend = r.trend(od, do, dziennie)
    assert [t["okres"] for t in trend] == [
        "2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
    assert [t["liczba"] for t in trend] == [2, 0, 0, 1, 4, 0, 1]


def test_trend_tygodniowy_nie_gubi_ostatniego_niepelnego_tygodnia():
    od, do = date(2026, 1, 1), date(2026, 2, 9)            # 40 dni
    trend = r.trend(od, do, {date(2026, 2, 9): 5})
    assert len(trend) == 6
    assert trend[-1] == {"okres": "2026-02-05", "liczba": 5}


def test_trend_ignoruje_dni_spoza_okresu():
    trend = r.trend(date(2026, 3, 1), date(2026, 3, 2),
                    {date(2026, 2, 28): 9, date(2026, 3, 1): 1, date(2026, 3, 3): 9})
    assert trend == [{"okres": "2026-03-01", "liczba": 1}, {"okres": "2026-03-02", "liczba": 0}]


# ---------------------------------------------------------------
# Liczby pomocnicze
# ---------------------------------------------------------------

def test_zmiana_procentowa():
    assert r.zmiana_proc(15, 10) == 50.0
    assert r.zmiana_proc(5, 10) == -50.0
    assert r.zmiana_proc(0, 3) == -100.0
    assert r.zmiana_proc(4, 0) is None


def test_kategorie_z_porownaniem_zachowuja_te_ktore_zniknely():
    wynik = r.kategorie_z_porownaniem({"Siec": 2}, {"Poczta": 3})
    assert {"kategoria": "Poczta", "etykieta": "Poczta", "liczba": 0, "poprzednio": 3,
            "zmiana_proc": -100.0} in wynik


def test_kategoria_pusta_jest_na_koncu_przy_remisie():
    wynik = r.kategorie_z_porownaniem({None: 1, "Siec": 1, "Bezpieczenstwo": 1}, {})
    assert [w["kategoria"] for w in wynik] == ["Bezpieczenstwo", "Siec", None]


def test_nieznany_priorytet_jest_zliczany_osobno():
    wynik = r.priorytety_w_kolejnosci({"Wysoki": 2, None: 1})
    assert wynik[-1] == {"priorytet": None, "liczba": 1}
    assert [w["priorytet"] for w in wynik[:4]] == r.KOLEJNOSC_PRIORYTETOW


# ---------------------------------------------------------------
# Rekomendacje
# ---------------------------------------------------------------

def _podsumowanie(**zmiany):
    bazowe = {"zgloszen": 10, "procent_w_terminie_sla": 100.0,
              "rozwiazanych_z_terminem": 10, "otwartych_po_terminie": 0}
    return {**bazowe, **zmiany}


def _kat(nazwa, liczba, zmiana=None, poprzednio=0):
    return {"kategoria": nazwa, "etykieta": r.etykieta_kategorii(nazwa), "liczba": liczba,
            "poprzednio": poprzednio, "zmiana_proc": zmiana}


def test_brak_zgloszen():
    assert r.rekomendacje(_podsumowanie(zgloszen=0), [], []) == [
        "W wybranym okresie nie było zgłoszeń."]


def test_spokojny_okres_ma_jedna_uspokajajaca_rekomendacje():
    wynik = r.rekomendacje(_podsumowanie(), [_kat("Siec", 2), _kat("Poczta", 2)], [])
    assert wynik == ["Brak niepokojących sygnałów w wybranym okresie."]


def test_dominujaca_kategoria():
    wynik = r.rekomendacje(_podsumowanie(), [_kat("Peryferia", 4)], [])
    assert wynik == ["40% zgłoszeń dotyczy kategorii Peryferia — to główne źródło "
                     "problemów w tym okresie."]


def test_male_liczby_nie_daja_wnioskow():
    """2 z 2 zgloszen to 100%, ale to za malo, by cokolwiek wnioskowac."""
    wynik = r.rekomendacje(_podsumowanie(zgloszen=2), [_kat("Siec", 2, zmiana=100.0)],
                           [{"problem": "VPN", "liczba": 2}])
    assert wynik == ["Brak niepokojących sygnałów w wybranym okresie."]


def test_wzrost_kategorii():
    wynik = r.rekomendacje(_podsumowanie(zgloszen=20),
                           [_kat("Poczta", 6, zmiana=200.0, poprzednio=2)], [])
    assert any("wzrosła o 200% (2 → 6)" in w for w in wynik)


def test_maly_przyrost_nie_jest_trendem():
    """2 → 4 to +100%, ale dwa zgloszenia wiecej to jeszcze nie wniosek."""
    wynik = r.rekomendacje(_podsumowanie(zgloszen=20),
                           [_kat("Poczta", 4, zmiana=100.0, poprzednio=2)], [])
    assert not any("wzrosła" in w for w in wynik)


def test_tylko_dwa_najwieksze_wzrosty():
    kategorie = [_kat("Siec", 9, 800.0, 1), _kat("Poczta", 5, 400.0, 1),
                 _kat("Sprzet", 4, 300.0, 1)]
    wynik = r.rekomendacje(_podsumowanie(zgloszen=100), kategorie, [])
    wzrosty = [w for w in wynik if "wzrosła" in w]
    assert len(wzrosty) == 2 and "Sieć" in wzrosty[0] and "Poczta" in wzrosty[1]


def test_liczba_rekomendacji_jest_ograniczona_a_najwazniejsze_sa_pierwsze():
    kategorie = [_kat("Bezpieczenstwo", 40, 300.0, 10), _kat("Siec", 40, 300.0, 10)]
    podsumowanie = _podsumowanie(zgloszen=80, procent_w_terminie_sla=50.0,
                                 otwartych_po_terminie=7)
    wynik = r.rekomendacje(podsumowanie, kategorie, [{"problem": "VPN", "liczba": 30}])
    assert len(wynik) == r.MAX_REKOMENDACJI
    assert wynik[0].startswith("Odnotowano 40 incydentów bezpieczeństwa")
    assert wynik[1].startswith("W terminie SLA")
    assert wynik[2] == "7 otwartych zgłoszeń przekroczyło już termin SLA."


@pytest.mark.parametrize("n,forma", [
    (1, "zgłoszenie"), (2, "zgłoszenia"), (4, "zgłoszenia"), (5, "zgłoszeń"),
    (12, "zgłoszeń"), (14, "zgłoszeń"), (22, "zgłoszenia"), (0, "zgłoszeń"),
    (101, "zgłoszeń"), (112, "zgłoszeń"), (124, "zgłoszenia"),
])
def test_odmiana_po_liczebniku(n, forma):
    assert r.odmiana(n, "zgłoszenie", "zgłoszenia", "zgłoszeń") == forma


def test_kazdy_rdzen_modulu_ai_ma_czytelna_etykiete():
    """Nowe slowo kluczowe bez etykiety pokazaloby klientowi „drukark"."""
    from app.domain.ai import KEYWORDS
    assert set(KEYWORDS) <= set(r.ETYKIETY_PROBLEMOW)


def test_kazda_kategoria_ma_etykiete():
    from app.domain.ai import CATEGORIES
    assert set(r.ETYKIETY_KATEGORII) == set(CATEGORIES)


def test_sla_ponizej_progu_tylko_przy_wystarczajacej_liczbie_danych():
    nisko = _podsumowanie(procent_w_terminie_sla=60.0, rozwiazanych_z_terminem=5)
    za_malo = _podsumowanie(procent_w_terminie_sla=0.0, rozwiazanych_z_terminem=4)
    assert any("W terminie SLA rozwiązano 60%" in w for w in r.rekomendacje(nisko, [], []))
    assert not any("W terminie SLA" in w for w in r.rekomendacje(za_malo, [], []))
