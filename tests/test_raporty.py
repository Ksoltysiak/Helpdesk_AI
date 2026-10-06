"""Testy raportow dla klientow — poprawnosc liczb, granice okresu, odpornosc.

Dane sa budowane recznie dla marca 2026 (okres zawsze w przeszlosci, wiec
wyniki nie zaleza od dnia uruchomienia testow). Oczekiwane liczby policzono
na kartce — kazda wartosc w asercjach da sie odtworzyc z tabeli ponizej.

Klient 3 („Firma Bez Zgloszen" w conftest) dostaje zgloszenia testowe:

  id   utworzono              kat.            prior.     status      rozwiazano / termin SLA
  101  03-02 08:00            Siec            Wysoki     Zamkniete   audyt 10:00 (2 h)  / 12:00  -> w terminie
  102  03-05T09:00 (zapis T)  Siec            Krytyczny  Rozwiazane  audyt 13:00 (4 h)  / 10:00  -> po terminie
  103  03-10 23:59:59         Peryferia       Niski      Zamkniete   brak audytu, closed_at +12 h -> w terminie
  104  03-31 23:59:59         Siec            Sredni     Nowe        otwarte, termin minal       -> po terminie
  105  04-01 00:00:00         Siec            Sredni     Nowe        POZA okresem (pierwsza sekunda kwietnia)
  106  02-28 23:59:59         Peryferia       Niski      Nowe        okres poprzedni
  107  03-15 08:00            Sprzet          Sredni     Zamkniete   rozwiazane 2x, ostatnio 20:00 (12 h) / 16:00 -> po terminie
  108  03-20 10:00            Bezpieczenstwo  Krytyczny  W trakcie   bez terminu SLA
  109  03-03 12:00            (klient 1) Poczta, Sredni, Nowe — sprawdza izolacje klientow
"""

import json
import sqlite3

import pytest

from app import config as db_module

pytestmark = pytest.mark.integration

MARZEC = "od=2026-03-01&do=2026-03-31"


def _zgloszenie(conn, tid, utworzono, kategoria, priorytet, status, *,
                klient=3, termin=None, zamknieto=None):
    conn.execute(
        """INSERT INTO tickets (id, title, description, category, priority, status,
                                created_by, client_id, ai_categorized, sla_deadline,
                                created_at, updated_at, closed_at)
           VALUES (?,?,?,?,?,?,1,?,1,?,?,?,?)""",
        (tid, f"Zgloszenie {tid}", "opis", kategoria, priorytet, status, klient,
         termin, utworzono, utworzono, zamknieto),
    )


def _audyt(conn, tid, akcja, nowa, kiedy="2026-03-01 00:00:00"):
    conn.execute(
        "INSERT INTO audit_log (ticket_id, user_id, action, new_value, timestamp)"
        " VALUES (?,?,?,?,?)", (tid, None, akcja, nowa, kiedy))


def _ai(conn, tid, dopasowania):
    tresc = dopasowania if isinstance(dopasowania, str) else json.dumps(
        {"kategoria": "x", "dopasowania": dopasowania})
    _audyt(conn, tid, "Kategoryzacja AI", tresc)


@pytest.fixture
def dane(app):
    conn = sqlite3.connect(db_module.DB_PATH)
    _zgloszenie(conn, 101, "2026-03-02 08:00:00", "Siec", "Wysoki", "Zamkniete",
                termin="2026-03-02 12:00:00", zamknieto="2026-03-03 09:00:00")
    _audyt(conn, 101, "Zmiana statusu", "Rozwiazane", "2026-03-02 10:00:00")
    _ai(conn, 101, ["vpn"])

    _zgloszenie(conn, 102, "2026-03-05T09:00:00", "Siec", "Krytyczny", "Rozwiazane",
                termin="2026-03-05T10:00:00")
    _audyt(conn, 102, "Zmiana statusu", "Rozwiazane", "2026-03-05 13:00:00")
    _ai(conn, 102, ["vpn", "router"])

    _zgloszenie(conn, 103, "2026-03-10 23:59:59", "Peryferia", "Niski", "Zamkniete",
                termin="2026-03-11 23:59:59", zamknieto="2026-03-11 11:59:59")
    _ai(conn, 103, "to nie jest json{")

    _zgloszenie(conn, 104, "2026-03-31 23:59:59", "Siec", "Sredni", "Nowe",
                termin="2026-04-01 07:59:59")
    _ai(conn, 104, ["vpn"])

    _zgloszenie(conn, 105, "2026-04-01 00:00:00", "Siec", "Sredni", "Nowe")
    _ai(conn, 105, ["vpn"])

    _zgloszenie(conn, 106, "2026-02-28 23:59:59", "Peryferia", "Niski", "Nowe")

    _zgloszenie(conn, 107, "2026-03-15 08:00:00", "Sprzet", "Sredni", "Zamkniete",
                termin="2026-03-15 16:00:00", zamknieto="2026-03-16 08:00:00")
    _audyt(conn, 107, "Zmiana statusu", "Rozwiazane", "2026-03-15 09:00:00")
    _audyt(conn, 107, "Zmiana statusu", "W trakcie", "2026-03-15 11:00:00")
    _audyt(conn, 107, "Zmiana statusu", "Rozwiazane", "2026-03-15 20:00:00")
    _ai(conn, 107, [1, None, "monitor"])

    _zgloszenie(conn, 108, "2026-03-20 10:00:00", "Bezpieczenstwo", "Krytyczny", "W trakcie")
    _ai(conn, 108, ["phishing"])
    _ai(conn, 108, ["phishing"])     # zdublowany wpis nie moze liczyc sie dwa razy

    _zgloszenie(conn, 109, "2026-03-03 12:00:00", "Poczta", "Sredni", "Nowe", klient=1)
    _ai(conn, 109, ["outlook"])
    conn.commit()
    conn.close()


def _raport(client, naglowki, zapytanie):
    resp = client.get(f"/api/reports?{zapytanie}", headers=naglowki)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


# ---------------------------------------------------------------
# Dostep
# ---------------------------------------------------------------

def test_raport_wymaga_zalogowania(client):
    assert client.get("/api/reports").status_code == 401


def test_pracownik_nie_ma_dostepu_do_raportow(client, pracownik):
    assert client.get("/api/reports", headers=pracownik).status_code == 403


def test_administrator_ma_dostep_do_raportow(client):
    from conftest import _naglowek_dla
    assert client.get("/api/reports", headers=_naglowek_dla(4)).status_code == 200


# ---------------------------------------------------------------
# Liczby — porownanie z tabela w opisie modulu
# ---------------------------------------------------------------

def test_podsumowanie_klienta(client, technik, dane):
    p = _raport(client, technik, f"client_id=3&{MARZEC}")["podsumowanie"]
    assert p == {
        "zgloszen": 6,                     # 101-104, 107, 108
        "otwartych": 2,                    # 104, 108
        "rozwiazanych": 4,                 # 101, 102, 103, 107
        "procent_rozwiazanych": 66.7,
        "krytycznych": 2,                  # 102, 108
        "sredni_czas_rozwiazania_h": 7.5,  # (2 + 4 + 12 + 12) / 4
        "rozwiazanych_z_terminem": 4,
        "w_terminie_sla": 2,               # 101, 103
        "procent_w_terminie_sla": 50.0,
        "otwartych_po_terminie": 1,        # 104 (108 nie ma terminu)
    }


def test_ponowne_otwarcie_liczy_ostatnie_rozwiazanie(client, technik, dane):
    """107: pierwsze „rozwiazanie" po 1 h bylo pozorne — liczy sie drugie, po 12 h."""
    p = _raport(client, technik, "client_id=3&od=2026-03-15&do=2026-03-15")["podsumowanie"]
    assert p["sredni_czas_rozwiazania_h"] == 12.0
    assert p["w_terminie_sla"] == 0


def test_brak_wpisu_w_historii_liczy_zamkniecie(client, technik, dane):
    p = _raport(client, technik, "client_id=3&od=2026-03-10&do=2026-03-10")["podsumowanie"]
    assert p["sredni_czas_rozwiazania_h"] == 12.0
    assert p["w_terminie_sla"] == 1


def test_zapis_daty_z_litera_t_jest_liczony_poprawnie(client, technik, dane):
    """102 ma daty w zapisie ISO z „T" — porownanie tekstowe daloby zly wynik."""
    raport = _raport(client, technik, "client_id=3&od=2026-03-05&do=2026-03-05")
    assert raport["podsumowanie"]["zgloszen"] == 1
    assert raport["podsumowanie"]["sredni_czas_rozwiazania_h"] == 4.0
    assert raport["podsumowanie"]["w_terminie_sla"] == 0
    assert raport["trend"] == [{"okres": "2026-03-05", "liczba": 1}]


def test_granice_okresu_sa_pelnymi_dobami(client, technik, dane):
    """Ostatnia sekunda okresu nalezy do niego, pierwsza sekunda po nim — nie."""
    marzec = _raport(client, technik, f"client_id=3&{MARZEC}")
    kwiecien = _raport(client, technik, "client_id=3&od=2026-04-01&do=2026-04-01")
    assert marzec["trend"][-1] == {"okres": "2026-03-31", "liczba": 1}       # 104
    assert kwiecien["podsumowanie"]["zgloszen"] == 1                          # 105


def test_rozklad_kategorii_z_porownaniem(client, technik, dane):
    kategorie = _raport(client, technik, f"client_id=3&{MARZEC}")["wg_kategorii"]
    assert kategorie == [
        {"kategoria": "Siec", "etykieta": "Sieć", "liczba": 3, "poprzednio": 0,
         "zmiana_proc": None},
        {"kategoria": "Bezpieczenstwo", "etykieta": "Bezpieczeństwo", "liczba": 1,
         "poprzednio": 0, "zmiana_proc": None},
        {"kategoria": "Peryferia", "etykieta": "Peryferia", "liczba": 1, "poprzednio": 1,
         "zmiana_proc": 0.0},
        {"kategoria": "Sprzet", "etykieta": "Sprzęt", "liczba": 1, "poprzednio": 0,
         "zmiana_proc": None},
    ]


def test_okres_poprzedni_ma_te_sama_dlugosc(client, technik, dane):
    raport = _raport(client, technik, f"client_id=3&{MARZEC}")
    assert raport["okres"] == {"od": "2026-03-01", "do": "2026-03-31", "dni": 31,
                               "grupowanie": "dzien"}
    assert raport["poprzedni_okres"] == {"od": "2026-01-29", "do": "2026-02-28",
                                         "zgloszen": 1, "zmiana_proc": 500.0}


def test_priorytety_w_kolejnosci_z_zerami(client, technik, dane):
    priorytety = _raport(client, technik, f"client_id=3&{MARZEC}")["wg_priorytetu"]
    assert priorytety == [
        {"priorytet": "Krytyczny", "liczba": 2},
        {"priorytet": "Wysoki", "liczba": 1},
        {"priorytet": "Sredni", "liczba": 2},
        {"priorytet": "Niski", "liczba": 1},
    ]


def test_trend_dzienny_obejmuje_dni_bez_zgloszen(client, technik, dane):
    trend = _raport(client, technik, f"client_id=3&{MARZEC}")["trend"]
    assert len(trend) == 31
    assert sum(d["liczba"] for d in trend) == 6
    assert {d["okres"] for d in trend if d["liczba"]} == {
        "2026-03-02", "2026-03-05", "2026-03-10", "2026-03-15", "2026-03-20", "2026-03-31"}


def test_najczestsze_problemy_sa_odporne_na_uszkodzone_wpisy(client, technik, dane):
    """Uszkodzony JSON (103) jest pomijany, liczby i null (107) tez,
    a zdublowany wpis AI (108) liczy sie raz."""
    problemy = _raport(client, technik, f"client_id=3&{MARZEC}")["najczestsze_problemy"]
    assert problemy == [
        {"problem": "VPN", "liczba": 3},
        {"problem": "monitor", "liczba": 1},
        {"problem": "phishing", "liczba": 1},
        {"problem": "router", "liczba": 1},
    ]


def test_rdzenie_tego_samego_problemu_licza_sie_raz(client, technik, app):
    """„haslo" i „hasla" to jeden problem — zgloszenie z oboma liczy sie raz."""
    conn = sqlite3.connect(db_module.DB_PATH)
    _zgloszenie(conn, 201, "2026-05-04 10:00:00", "Konta i dostep", "Sredni", "Nowe")
    _ai(conn, 201, ["haslo", "hasla", "nieznany-rdzen"])
    _zgloszenie(conn, 202, "2026-05-05 10:00:00", "Konta i dostep", "Sredni", "Nowe")
    _ai(conn, 202, ["hasla"])
    conn.commit()
    conn.close()
    problemy = _raport(client, technik,
                       "client_id=3&od=2026-05-01&do=2026-05-31")["najczestsze_problemy"]
    assert problemy == [{"problem": "hasło", "liczba": 2},
                        {"problem": "nieznany-rdzen", "liczba": 1}]


def test_rekomendacje_wynikaja_z_liczb(client, technik, dane):
    rekomendacje = _raport(client, technik, f"client_id=3&{MARZEC}")["rekomendacje"]
    tekst = " ".join(rekomendacje)
    assert "50% zgłoszeń dotyczy kategorii Sieć" in tekst
    assert "Odnotowano 1 incydent bezpieczeństwa" in tekst
    assert "problem: VPN (3 zgłoszenia)" in tekst
    assert "1 otwarte zgłoszenie przekroczyło już termin SLA" in tekst
    # Tylko 4 rozwiazane z terminem — za malo na wniosek o SLA.
    assert "W terminie SLA" not in tekst


# ---------------------------------------------------------------
# Izolacja klientow i raport zbiorczy
# ---------------------------------------------------------------

def test_raport_klienta_nie_zawiera_danych_innych_firm(client, technik, dane):
    raport = _raport(client, technik, f"client_id=1&{MARZEC}")
    assert raport["klient"] == {"id": 1, "name": "Firma Testowa A"}
    assert raport["podsumowanie"]["zgloszen"] == 1
    assert [k["kategoria"] for k in raport["wg_kategorii"]] == ["Poczta"]
    assert raport["najczestsze_problemy"] == [{"problem": "Outlook", "liczba": 1}]


def test_raport_bez_klienta_obejmuje_wszystkie_firmy(client, technik, dane):
    raport = _raport(client, technik, MARZEC)
    assert raport["klient"] is None
    assert raport["podsumowanie"]["zgloszen"] == 7


def test_pusty_okres_daje_zera_a_nie_bledy(client, technik, dane):
    raport = _raport(client, technik, "client_id=2&od=2026-03-01&do=2026-03-31")
    p = raport["podsumowanie"]
    assert p["zgloszen"] == 0 and p["otwartych"] == 0
    assert p["procent_rozwiazanych"] is None
    assert p["sredni_czas_rozwiazania_h"] is None
    assert p["procent_w_terminie_sla"] is None
    assert raport["wg_kategorii"] == [] and raport["najczestsze_problemy"] == []
    assert raport["rekomendacje"] == ["W wybranym okresie nie było zgłoszeń."]


# ---------------------------------------------------------------
# Okres raportu
# ---------------------------------------------------------------

def test_domyslnie_ostatnie_30_dni(client, technik):
    from datetime import datetime, timedelta, timezone
    dzis = datetime.now(timezone.utc).date()
    okres = _raport(client, technik, "")["okres"]
    assert okres["do"] == dzis.isoformat()
    assert okres["od"] == (dzis - timedelta(days=29)).isoformat()


def test_nowe_zgloszenie_trafia_do_dzisiejszego_raportu(client, technik, pracownik):
    przed = _raport(client, technik, "client_id=1")["podsumowanie"]["zgloszen"]
    client.post("/api/tickets", headers=pracownik,
                json={"title": "Drukarka", "description": "brak tonera"})
    po = _raport(client, technik, "client_id=1")["podsumowanie"]["zgloszen"]
    assert po == przed + 1


def test_tygodniowy_trend_dla_kwartalu(client, technik, dane):
    raport = _raport(client, technik, "client_id=3&od=2026-01-01&do=2026-03-31")
    assert raport["okres"]["grupowanie"] == "tydzien"
    assert len(raport["trend"]) == 13                   # 90 dni = 12 pelnych tygodni + 6 dni
    assert raport["trend"][0]["okres"] == "2026-01-01"
    assert sum(t["liczba"] for t in raport["trend"]) == raport["podsumowanie"]["zgloszen"] == 7


def test_miesieczny_trend_dla_roku(client, technik, dane):
    raport = _raport(client, technik, "client_id=3&od=2025-04-01&do=2026-03-31")
    assert raport["okres"]["grupowanie"] == "miesiac"
    assert [t["okres"] for t in raport["trend"]][:2] == ["2025-04", "2025-05"]
    assert raport["trend"][-1] == {"okres": "2026-03", "liczba": 6}
    assert len(raport["trend"]) == 12


def test_okres_366_dni_jest_dozwolony(client, technik):
    assert client.get("/api/reports?od=2025-01-01&do=2026-01-01",
                      headers=technik).status_code == 200


@pytest.mark.parametrize("zapytanie", [
    "od=2026-13-01",                    # nie ma 13. miesiaca
    "od=2026-02-30",                    # nie ma 30 lutego
    "od=abc",
    "od=2026-3-1",                      # bez zer wiodacych
    "od=20260301",                      # zapis bez kresek
    "od=2026-03-01T00:00",
    "od=2026-03-31&do=2026-03-01",      # odwrocony zakres
    "od=2025-01-01&do=2026-01-02",      # 367 dni
    "od=1999-12-31&do=2000-01-01",      # przed dolna granica
    "od=0001-01-01&do=0001-01-31",      # przepelnienie przy okresie poprzednim
    "od=9999-12-01&do=9999-12-31",      # przyszlosc
    "od=%00%00",
    "od=2026-03-01%27%20OR%201%3D1--",  # proba wstrzykniecia SQL
])
def test_nieprawidlowy_okres_daje_400(client, technik, zapytanie):
    resp = client.get(f"/api/reports?{zapytanie}", headers=technik)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


@pytest.mark.parametrize("wartosc", ["abc", "-1", "1.5", "%201", "1%20OR%201=1",
                                     "%EF%BC%91",            # cyfra pelnej szerokosci
                                     "9" * 30])
def test_nieprawidlowy_klient_daje_400(client, technik, wartosc):
    assert client.get(f"/api/reports?client_id={wartosc}", headers=technik).status_code == 400


def test_nieistniejacy_klient_daje_404(client, technik):
    assert client.get("/api/reports?client_id=999", headers=technik).status_code == 404
    assert client.get("/api/reports?client_id=" + "9" * 18, headers=technik).status_code == 404


# ---------------------------------------------------------------
# Wydajnosc — raport ma korzystac z indeksow, a nie przegladac tabel
# ---------------------------------------------------------------

def _plan(sql, params):
    conn = sqlite3.connect(db_module.DB_PATH)
    plan = " | ".join(w[3] for w in conn.execute("EXPLAIN QUERY PLAN " + sql, params))
    conn.close()
    return plan


OKRES = ("2026-03-01 00:00:00", "2026-04-01 00:00:00")


def test_raport_klienta_czyta_tylko_indeks(app):
    """Indeks pokrywajacy: raport nie siega do wierszy z dlugimi opisami."""
    plan = _plan("SELECT t.category, COUNT(*) FROM tickets t WHERE t.client_id = ?"
                 " AND t.created_at >= ? AND t.created_at < ? GROUP BY t.category",
                 (1, *OKRES))
    assert "COVERING INDEX idx_tickets_klient_raport" in plan


def test_raport_wszystkich_klientow_czyta_tylko_indeks(app):
    plan = _plan("SELECT t.priority, COUNT(*) FROM tickets t WHERE t.created_at >= ?"
                 " AND t.created_at < ? GROUP BY t.priority", OKRES)
    assert "COVERING INDEX idx_tickets_raport" in plan


def test_chwila_rozwiazania_pochodzi_z_indeksu_czesciowego(app):
    plan = _plan("SELECT MAX(a.timestamp) FROM audit_log a WHERE a.ticket_id = ?"
                 " AND a.action = 'Zmiana statusu' AND a.new_value = 'Rozwiazane'", (1,))
    assert "idx_audit_rozwiazanie" in plan
