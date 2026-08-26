"""Testy integracyjne zgloszen: kontrola dostepu wg rol, tworzenie,
maszyna stanow, notatki i sciezka audytu.
"""

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------
# Widocznosc danych wg roli (RBAC) — najwazniejsza granica bezpieczenstwa
# ---------------------------------------------------------------

def test_pracownik_widzi_wylacznie_wlasne_zgloszenia(client, pracownik):
    data = client.get("/api/tickets", headers=pracownik).get_json()
    assert data["total"] == 2
    assert {t["created_by"] for t in data["tickets"]} == {1}


def test_drugi_pracownik_widzi_inny_zestaw(client, pracownik2):
    data = client.get("/api/tickets", headers=pracownik2).get_json()
    assert {t["created_by"] for t in data["tickets"]} == {2}


def test_technik_widzi_wszystkie_zgloszenia(client, technik):
    assert client.get("/api/tickets", headers=technik).get_json()["total"] == 4


def test_pracownik_nie_odczyta_cudzego_zgloszenia(client, pracownik):
    """Zgloszenie #3 nalezy do pracownika o id=2."""
    assert client.get("/api/tickets/3", headers=pracownik).status_code == 403


def test_pracownik_odczyta_wlasne_zgloszenie(client, pracownik):
    assert client.get("/api/tickets/1", headers=pracownik).status_code == 200


def test_nieistniejace_zgloszenie_daje_404(client, technik):
    assert client.get("/api/tickets/9999", headers=technik).status_code == 404


# ---------------------------------------------------------------
# Filtrowanie (tylko technik/admin)
# ---------------------------------------------------------------

@pytest.mark.parametrize("filtr,oczekiwane", [
    ("status=Nowe", 2),
    ("status=Zamkniete", 1),
    ("priority=Krytyczny", 1),
    ("category=Siec", 1),
    ("status=Nowe&priority=Niski", 1),
])
def test_technik_filtruje_liste(client, technik, filtr, oczekiwane):
    assert client.get(f"/api/tickets?{filtr}", headers=technik).get_json()["total"] == oczekiwane


def test_filtr_nie_omija_izolacji_pracownika(client, pracownik):
    """Pracownik nie moze filtrem dosiegnac cudzych zgloszen."""
    data = client.get("/api/tickets?status=Nowe", headers=pracownik).get_json()
    assert {t["created_by"] for t in data["tickets"]} == {1}


# ---------------------------------------------------------------
# Nazwiska dolaczane do zgloszen
# ---------------------------------------------------------------

def test_lista_zawiera_nazwisko_zglaszajacego(client, technik):
    data = client.get("/api/tickets", headers=technik).get_json()
    zgloszenie = next(t for t in data["tickets"] if t["id"] == 1)
    assert zgloszenie["created_by_name"] == "Katarzyna Nowak"


def test_szczegoly_zawieraja_nazwisko_przypisanego_technika(client, technik):
    data = client.get("/api/tickets/2", headers=technik).get_json()
    assert data["assigned_to_name"] == "Marek Lewandowski"


def test_nieprzypisane_zgloszenie_ma_puste_nazwisko(client, technik):
    assert client.get("/api/tickets/1", headers=technik).get_json()["assigned_to_name"] is None


# ---------------------------------------------------------------
# Tworzenie zgloszenia
# ---------------------------------------------------------------

def test_pracownik_tworzy_zgloszenie_z_kategoryzacja_ai(client, pracownik):
    resp = client.post("/api/tickets", headers=pracownik,
                       json={"title": "Nie dziala VPN", "description": "Blad TLS handshake"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["kategoryzacja_ai"]["kategoria"] == "Siec"
    assert data["sla_deadline"]


def test_nowe_zgloszenie_ma_status_nowe_i_autora(client, pracownik):
    tid = client.post("/api/tickets", headers=pracownik,
                      json={"title": "Test", "description": "Opis testowy"}).get_json()["id"]
    data = client.get(f"/api/tickets/{tid}", headers=pracownik).get_json()
    assert data["status"] == "Nowe"
    assert data["created_by"] == 1
    assert data["ai_categorized"] is True


def test_technik_nie_moze_tworzyc_zgloszen(client, technik):
    """Zgloszenia sklada pracownik — technik je obsluguje."""
    resp = client.post("/api/tickets", headers=technik,
                       json={"title": "Test", "description": "Opis"})
    assert resp.status_code == 403


@pytest.mark.parametrize("dane", [
    {"title": "", "description": "Opis"},
    {"title": "Tytul", "description": ""},
    {"title": "Tylko tytul"},
    {},
])
def test_brak_wymaganych_pol_daje_400(client, pracownik, dane):
    assert client.post("/api/tickets", headers=pracownik, json=dane).status_code == 400


def test_zbyt_dlugi_tytul_jest_odrzucany(client, pracownik):
    resp = client.post("/api/tickets", headers=pracownik,
                       json={"title": "x" * 201, "description": "Opis"})
    assert resp.status_code == 400


def test_zbyt_dlugi_opis_jest_odrzucany(client, pracownik):
    resp = client.post("/api/tickets", headers=pracownik,
                       json={"title": "Tytul", "description": "x" * 5001})
    assert resp.status_code == 400


def test_tytul_o_granicznej_dlugosci_jest_akceptowany(client, pracownik):
    resp = client.post("/api/tickets", headers=pracownik,
                       json={"title": "x" * 200, "description": "Opis"})
    assert resp.status_code == 201


# ---------------------------------------------------------------
# Maszyna stanow w praktyce
# ---------------------------------------------------------------

def test_technik_podejmuje_zgloszenie(client, technik):
    resp = client.patch("/api/tickets/1", headers=technik, json={"status": "W trakcie"})
    assert resp.status_code == 200
    assert client.get("/api/tickets/1", headers=technik).get_json()["status"] == "W trakcie"


def test_podjecie_przypisuje_zgloszenie_do_technika(client, technik):
    """Zgloszenie #1 nie ma przypisanej osoby — podjecie ma to ustawic."""
    client.patch("/api/tickets/1", headers=technik, json={"status": "W trakcie"})
    assert client.get("/api/tickets/1", headers=technik).get_json()["assigned_to"] == 3


def test_niedozwolone_przejscie_jest_odrzucane(client, technik):
    resp = client.patch("/api/tickets/1", headers=technik, json={"status": "Zamkniete"})
    assert resp.status_code == 400
    assert resp.get_json()["dozwolone"] == ["W trakcie"]


def test_zgloszenie_zamkniete_nie_zmienia_juz_statusu(client, technik):
    resp = client.patch("/api/tickets/4", headers=technik, json={"status": "W trakcie"})
    assert resp.status_code == 400


def test_zamkniecie_ustawia_date_zamkniecia(client, technik):
    client.patch("/api/tickets/2", headers=technik, json={"status": "Rozwiazane"})
    client.patch("/api/tickets/2", headers=technik, json={"status": "Zamkniete"})
    assert client.get("/api/tickets/2", headers=technik).get_json()["closed_at"] is not None


def test_pracownik_nie_moze_zmienic_statusu(client, pracownik):
    assert client.patch("/api/tickets/1", headers=pracownik,
                        json={"status": "W trakcie"}).status_code == 403


def test_nieznana_kategoria_jest_odrzucana(client, technik):
    resp = client.patch("/api/tickets/1", headers=technik, json={"category": "Nieistniejaca"})
    assert resp.status_code == 400


def test_patch_bez_zadnego_pola_daje_400(client, technik):
    assert client.patch("/api/tickets/1", headers=technik, json={}).status_code == 400


def test_patch_nieistniejacego_zgloszenia_daje_404(client, technik):
    assert client.patch("/api/tickets/9999", headers=technik,
                        json={"status": "W trakcie"}).status_code == 404


# ---------------------------------------------------------------
# Reczna korekta kategorii i przypisania przez technika
# ---------------------------------------------------------------

def test_technik_zmienia_kategorie(client, technik):
    resp = client.patch("/api/tickets/1", headers=technik, json={"category": "Sprzet"})
    assert resp.status_code == 200
    assert resp.get_json()["zaktualizowano"] == ["category"]
    assert client.get("/api/tickets/1", headers=technik).get_json()["category"] == "Sprzet"


def test_zmiana_kategorii_trafia_do_audytu(client, technik):
    client.patch("/api/tickets/1", headers=technik, json={"category": "Sprzet"})
    audyt = client.get("/api/tickets/1/audit", headers=technik).get_json()
    wpis = next(w for w in audyt if w["action"] == "Zmiana kategorii")
    assert wpis["old"] == "Bezpieczenstwo" and wpis["new"] == "Sprzet"


def test_technik_przypisuje_zgloszenie_innej_osobie(client, technik):
    resp = client.patch("/api/tickets/1", headers=technik, json={"assigned_to": 4})
    assert resp.status_code == 200
    assert client.get("/api/tickets/1", headers=technik).get_json()["assigned_to"] == 4


@pytest.mark.parametrize("wartosc", ["3", 1.5, None, {"id": 3}])
def test_przypisanie_musi_byc_liczba_calkowita(client, technik, wartosc):
    assert client.patch("/api/tickets/1", headers=technik,
                        json={"assigned_to": wartosc}).status_code == 400


def test_mozna_zmienic_kilka_pol_naraz(client, technik):
    resp = client.patch("/api/tickets/1", headers=technik,
                        json={"status": "W trakcie", "category": "Sprzet"})
    assert set(resp.get_json()["zaktualizowano"]) == {"status", "category"}


def test_notatka_do_nieistniejacego_zgloszenia_daje_404(client, technik):
    assert client.post("/api/tickets/9999/notes", headers=technik,
                       json={"content": "Test"}).status_code == 404


def test_notatka_moze_byc_jawna_dla_zglaszajacego(client, technik, pracownik):
    client.post("/api/tickets/1/notes", headers=technik,
                json={"content": "Widoczna dla Ciebie", "internal": False})
    tresci = [n["content"] for n in client.get("/api/tickets/1", headers=pracownik).get_json()["notes"]]
    assert "Widoczna dla Ciebie" in tresci


# ---------------------------------------------------------------
# Endpoint testowy modulu AI
# ---------------------------------------------------------------

def test_endpoint_ai_zwraca_kategorie_i_priorytet(client, pracownik):
    resp = client.post("/api/ai/categorize", headers=pracownik,
                       json={"title": "Nie dziala VPN", "description": "Blad TLS"})
    assert resp.status_code == 200
    wynik = resp.get_json()
    assert wynik["kategoria"] == "Siec"
    assert wynik["priorytet"] == "Wysoki"


def test_endpoint_ai_zwraca_pewnosc_i_uzasadnienie(client, pracownik):
    """Technik ma widziec nie tylko decyzje, ale i jej podstawe."""
    wynik = client.post("/api/ai/categorize", headers=pracownik,
                        json={"title": "Nie dziala VPN", "description": "Blad TLS"}).get_json()
    assert 0.0 <= wynik["pewnosc"] <= 1.0
    assert wynik["wymaga_weryfikacji"] is False
    assert "vpn" in wynik["dopasowania"]


def test_nowe_zgloszenie_zapamietuje_pewnosc_ai(client, pracownik):
    """Pewnosc musi przetrwac w bazie — inaczej technik jej pozniej nie zobaczy."""
    tid = client.post("/api/tickets", headers=pracownik,
                      json={"title": "Nie dziala VPN", "description": "Blad TLS"}).get_json()["id"]
    dane = client.get(f"/api/tickets/{tid}", headers=pracownik).get_json()
    assert dane["ai_pewnosc"] is not None
    assert 0.0 <= dane["ai_pewnosc"] <= 1.0


def test_zgloszenie_nierozpoznane_ma_zerowa_pewnosc(client, pracownik):
    tid = client.post("/api/tickets", headers=pracownik,
                      json={"title": "Prosba o spotkanie",
                            "description": "Chcialbym umowic rozmowe"}).get_json()["id"]
    dane = client.get(f"/api/tickets/{tid}", headers=pracownik).get_json()
    assert dane["ai_pewnosc"] == 0.0


# ---------------------------------------------------------------
# Skutecznosc AI liczona z korekt technikow
# ---------------------------------------------------------------

def test_skutecznosc_ai_wymaga_roli_technika(client, pracownik):
    assert client.get("/api/ai/skutecznosc", headers=pracownik).status_code == 403


def test_skutecznosc_ai_zwraca_komplet_miar(client, technik):
    dane = client.get("/api/ai/skutecznosc", headers=technik).get_json()
    assert set(dane) == {"zgloszen_z_ai", "poprawionych_recznie", "skutecznosc",
                         "srednia_pewnosc", "wymaga_weryfikacji", "prog_pewnosci",
                         "najczestsze_pomylki"}


def test_reczna_korekta_obniza_skutecznosc(client, technik, pracownik):
    """Zmiana kategorii przez technika to sygnal pomylki modulu."""
    client.post("/api/tickets", headers=pracownik,
                json={"title": "Nie dziala VPN", "description": "Blad TLS"})

    przed = client.get("/api/ai/skutecznosc", headers=technik).get_json()
    client.patch("/api/tickets/1", headers=technik, json={"category": "Sprzet"})
    po = client.get("/api/ai/skutecznosc", headers=technik).get_json()

    assert po["poprawionych_recznie"] > przed["poprawionych_recznie"]
    assert po["skutecznosc"] < przed["skutecznosc"]


def test_skutecznosc_pokazuje_kierunek_pomylek(client, technik):
    """Zestawienie ma wprost wskazywac, ktore kategorie myla sie najczesciej."""
    client.patch("/api/tickets/1", headers=technik, json={"category": "Sprzet"})
    dane = client.get("/api/ai/skutecznosc", headers=technik).get_json()
    pomylki = dane["najczestsze_pomylki"]
    assert any(p["z"] == "Bezpieczenstwo" and p["na"] == "Sprzet" for p in pomylki)


def test_skutecznosc_bez_zgloszen_nie_dzieli_przez_zero(client, technik, app):
    import sqlite3
    import db as db_module
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("DELETE FROM audit_log")
    conn.execute("DELETE FROM notes")
    conn.execute("DELETE FROM tickets")
    conn.commit(); conn.close()

    dane = client.get("/api/ai/skutecznosc", headers=technik).get_json()
    assert dane["skutecznosc"] is None
    assert dane["zgloszen_z_ai"] == 0


def test_endpoint_ai_dziala_z_samym_tytulem(client, pracownik):
    assert client.post("/api/ai/categorize", headers=pracownik,
                       json={"title": "phishing"}).status_code == 200


def test_endpoint_ai_bez_danych_daje_400(client, pracownik):
    assert client.post("/api/ai/categorize", headers=pracownik, json={}).status_code == 400


def test_endpoint_ai_wymaga_zalogowania(client):
    assert client.post("/api/ai/categorize", json={"title": "test"}).status_code == 401


# ---------------------------------------------------------------
# Notatki — widocznosc wewnetrznych
# ---------------------------------------------------------------

def test_pracownik_nie_widzi_notatek_wewnetrznych(client, pracownik):
    notatki = client.get("/api/tickets/1", headers=pracownik).get_json()["notes"]
    assert all(n["internal"] is False for n in notatki)
    assert not any("wewnetrzna" in n["content"] for n in notatki)


def test_technik_widzi_wszystkie_notatki(client, technik):
    notatki = client.get("/api/tickets/1", headers=technik).get_json()["notes"]
    assert len(notatki) == 2
    assert any(n["internal"] for n in notatki)


def test_technik_dodaje_notatke(client, technik):
    resp = client.post("/api/tickets/1/notes", headers=technik,
                       json={"content": "Sprawdzam logi", "internal": True})
    assert resp.status_code == 201
    assert len(client.get("/api/tickets/1", headers=technik).get_json()["notes"]) == 3


def test_pracownik_nie_moze_dodac_notatki(client, pracownik):
    assert client.post("/api/tickets/1/notes", headers=pracownik,
                       json={"content": "Test"}).status_code == 403


def test_pusta_notatka_jest_odrzucana(client, technik):
    assert client.post("/api/tickets/1/notes", headers=technik,
                       json={"content": ""}).status_code == 400


def test_zbyt_dluga_notatka_jest_odrzucana(client, technik):
    assert client.post("/api/tickets/1/notes", headers=technik,
                       json={"content": "x" * 2001}).status_code == 400


# ---------------------------------------------------------------
# Sciezka audytu
# ---------------------------------------------------------------

def test_zmiana_statusu_trafia_do_audytu(client, technik):
    client.patch("/api/tickets/1", headers=technik, json={"status": "W trakcie"})
    audyt = client.get("/api/tickets/1/audit", headers=technik).get_json()
    wpis = next(w for w in audyt if w["action"] == "Zmiana statusu")
    assert wpis["old"] == "Nowe" and wpis["new"] == "W trakcie"
    assert wpis["user"] == "Marek Lewandowski"


def test_utworzenie_i_kategoryzacja_sa_rejestrowane(client, pracownik, technik):
    tid = client.post("/api/tickets", headers=pracownik,
                      json={"title": "Nie dziala VPN", "description": "Blad TLS"}).get_json()["id"]
    akcje = [w["action"] for w in client.get(f"/api/tickets/{tid}/audit", headers=technik).get_json()]
    assert "Utworzenie" in akcje
    assert "Kategoryzacja AI" in akcje


def test_kategoryzacje_ai_podpisuje_system(client, pracownik, technik):
    tid = client.post("/api/tickets", headers=pracownik,
                      json={"title": "Test", "description": "Opis"}).get_json()["id"]
    audyt = client.get(f"/api/tickets/{tid}/audit", headers=technik).get_json()
    assert next(w for w in audyt if w["action"] == "Kategoryzacja AI")["user"] == "System AI"


def test_pracownik_nie_ma_dostepu_do_audytu(client, pracownik):
    assert client.get("/api/tickets/1/audit", headers=pracownik).status_code == 403


# ---------------------------------------------------------------
# Pulpit
# ---------------------------------------------------------------

def test_pulpit_zwraca_statystyki_i_rozklad_kategorii(client, technik):
    data = client.get("/api/dashboard", headers=technik).get_json()
    assert data["statystyki"]["otwarte"] == 3
    assert data["statystyki"]["krytyczne"] == 1
    assert {k["kategoria"] for k in data["wg_kategorii"]}
