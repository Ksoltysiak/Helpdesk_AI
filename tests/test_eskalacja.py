"""Testy eskalacji SLA, kolejki e-maili i procesu roboczego.

Dane testowe (conftest): wszystkie zgłoszenia mają termin SLA
2026-01-01 00:00 UTC. Aktywne są #1 (Krytyczny, bez opiekuna),
#2 (Średni, opiekun — technik id 3) i #3 (Niski, bez opiekuna); #4 jest
zamknięte. Technik ma id 3, administrator id 4.

Czas „teraz” jest w testach podawany jawnie — wynik nie zależy od dnia,
w którym uruchamia się testy.
"""

import smtplib
import sqlite3
import threading

import pytest

from app import config
from app.data import database
from app.domain import eskalacja as reguly
from app.zadania import __main__ as worker
from app.zadania import eskalacja, poczta

PRZED_TERMINEM = "2025-12-31 23:00:00"
CHWILE_PO = "2026-01-01 00:10:00"      # #1: 10 min z 30 do drugiego stopnia
POL_GODZINY_PO = "2026-01-01 00:40:00"  # #1 przekroczył połowę swojego SLA (1 h)
DAWNO_PO = "2026-03-01 00:00:00"


def baza():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def stopnie():
    with baza() as conn:
        return dict(conn.execute("SELECT id, eskalacja FROM tickets ORDER BY id").fetchall())


def powiadomienia_eskalacji():
    with baza() as conn:
        return [tuple(r) for r in conn.execute(
            "SELECT ticket_id, user_id FROM notifications WHERE typ = 'eskalacja'"
            " ORDER BY ticket_id, user_id").fetchall()]


def eskaluj(app, teraz):
    with app.app_context():
        return eskalacja.eskaluj(teraz)


# ---------------------------------------------------------------
# Reguły
# ---------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("spoznienie,priorytet,stopien", [
    (-0.1, "Krytyczny", 0),
    (0,    "Krytyczny", 1),    # w chwili terminu
    (0.49, "Krytyczny", 1),
    (0.5,  "Krytyczny", 2),    # połowa z 1 h
    (1.9,  "Wysoki",    1),
    (2,    "Wysoki",    2),    # połowa z 4 h
    (11.9, "Niski",     1),
    (12,   "Niski",     2),    # połowa z 24 h
    (11.9, None,        1),    # nieznany priorytet = najdłuższe SLA
])
def test_stopien_eskalacji(spoznienie, priorytet, stopien):
    assert reguly.stopien_eskalacji(spoznienie, priorytet) == stopien


ZGL = {"id": 5, "title": "VPN", "priority": "Wysoki", "assigned_to": None}


@pytest.mark.unit
def test_pierwszy_stopien_trafia_do_opiekuna_albo_technikow():
    z_opiekunem = reguly.powiadomienia_eskalacji({**ZGL, "assigned_to": 9}, 1, 0.2, [3, 7], [4])
    assert [p["user_id"] for p in z_opiekunem] == [9]
    bez = reguly.powiadomienia_eskalacji(ZGL, 1, 0.2, [3, 7], [4])
    assert [p["user_id"] for p in bez] == [3, 7]
    assert "bez opiekuna" in bez[0]["tresc"]


@pytest.mark.unit
def test_bez_technikow_pierwszy_stopien_trafia_do_administratorow():
    assert [p["user_id"] for p in reguly.powiadomienia_eskalacji(ZGL, 1, 0.2, [], [4])] == [4]


@pytest.mark.unit
@pytest.mark.parametrize("godzin,tekst", [(0.25, "15 min"), (2.0, "2 h"), (2.5, "2,5 h"), (30, "30 h")])
def test_drugi_stopien_trafia_do_administratorow_z_opoznieniem(godzin, tekst):
    [p] = reguly.powiadomienia_eskalacji(ZGL, 2, godzin, [3], [4])
    assert p["user_id"] == 4 and p["typ"] == "eskalacja"
    assert f"{tekst} po terminie" in p["tresc"]


@pytest.mark.unit
def test_brak_eskalacji_nikogo_nie_powiadamia():
    assert reguly.powiadomienia_eskalacji(ZGL, 0, -1, [3], [4]) == []


# ---------------------------------------------------------------
# Przebieg eskalacji na bazie
# ---------------------------------------------------------------

def test_przed_terminem_nic_sie_nie_dzieje(app):
    assert eskaluj(app, PRZED_TERMINEM) == 0
    assert powiadomienia_eskalacji() == []


def test_pierwszy_stopien(app):
    assert eskaluj(app, CHWILE_PO) == 3
    assert stopnie() == {1: 1, 2: 1, 3: 1, 4: 0}      # zamknięte pominięte
    # #1 i #3 bez opiekuna -> technicy, #2 -> jego opiekun (też technik 3).
    assert powiadomienia_eskalacji() == [(1, 3), (2, 3), (3, 3)]


def test_kolejny_przebieg_nie_powtarza_powiadomien(app):
    eskaluj(app, CHWILE_PO)
    assert eskaluj(app, CHWILE_PO) == 0
    assert len(powiadomienia_eskalacji()) == 3


def test_drugi_stopien_dochodzi_pozniej(app):
    eskaluj(app, CHWILE_PO)
    assert eskaluj(app, POL_GODZINY_PO) == 1          # tylko #1 (Krytyczny)
    assert stopnie()[1] == 2
    assert (1, 4) in powiadomienia_eskalacji()


def test_przeskok_o_dwa_stopnie_wysyla_powiadomienia_obu(app):
    eskaluj(app, DAWNO_PO)
    assert stopnie() == {1: 2, 2: 2, 3: 2, 4: 0}
    assert powiadomienia_eskalacji() == [(1, 3), (1, 4), (2, 3), (2, 4), (3, 3), (3, 4)]


def test_eskalacja_trafia_do_sciezki_audytu(app, client, technik):
    eskaluj(app, CHWILE_PO)
    wpis = client.get("/api/tickets/1/audit", headers=technik).get_json()[-1]
    assert wpis == {**wpis, "action": "Eskalacja SLA", "user": "System", "old": "0", "new": "1"}
    assert client.get("/api/tickets/1", headers=technik).get_json()["eskalacja"] == 1


def test_rozwiazane_zgloszenie_nie_jest_eskalowane(app, client, technik):
    client.patch("/api/tickets/2", headers=technik, json={"status": "Rozwiazane"})
    eskaluj(app, DAWNO_PO)
    assert stopnie()[2] == 0


def test_rownolegly_proces_nie_dubluje_eskalacji(app, monkeypatch):
    """Drugi proces podniósł stopień między odczytem a zapisem."""
    from app.data import powiadomienia as repo
    monkeypatch.setattr(repo, "podnies_stopien", lambda *a: False)
    assert eskaluj(app, CHWILE_PO) == 0
    assert powiadomienia_eskalacji() == []


# ---------------------------------------------------------------
# Kolejka e-maili
# ---------------------------------------------------------------

class SerwerPoczty:
    """Atrapa smtplib.SMTP / SMTP_SSL zapamiętująca wywołania."""

    def __init__(self, odrzuc=(), blad_polaczenia=False, blad_quit=False):
        self.wyslane, self.zdarzenia = [], []
        self.odrzuc, self.blad_polaczenia, self.blad_quit = set(odrzuc), blad_polaczenia, blad_quit

    def __call__(self, host, port, timeout=None, context=None):
        if self.blad_polaczenia:
            raise ConnectionRefusedError("brak serwera")
        self.zdarzenia.append(("polaczenie", host, port, context is not None))
        return self

    def starttls(self, context=None):
        self.zdarzenia.append(("starttls",))

    def login(self, user, haslo):
        self.zdarzenia.append(("login", user))

    def send_message(self, msg):
        if msg["To"] in self.odrzuc:
            raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"nie ma")})
        self.wyslane.append(msg)

    def quit(self):
        if self.blad_quit:
            raise smtplib.SMTPServerDisconnected("rozlaczono")
        self.zdarzenia.append(("quit",))


@pytest.fixture
def smtp(monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(config, "SMTP_PORT", 587)
    monkeypatch.setattr(config, "SMTP_TLS", "starttls")
    monkeypatch.setattr(config, "SMTP_USER", "")
    monkeypatch.setattr(config, "APP_URL", "")

    def podstaw(**opcje):
        serwer = SerwerPoczty(**opcje)
        monkeypatch.setattr(smtplib, "SMTP", serwer)
        monkeypatch.setattr(smtplib, "SMTP_SSL", serwer)
        return serwer
    return podstaw


def wyslij(app, teraz=CHWILE_PO):
    with app.app_context():
        return poczta.wyslij_zalegle(teraz)


def stan_kolejki():
    with baza() as conn:
        return [tuple(r) for r in conn.execute(
            "SELECT user_id, email_wyslany IS NOT NULL, email_proby FROM notifications"
            " ORDER BY id").fetchall()]


def ustaw_czas_powiadomien(teraz):
    with baza() as conn:
        conn.execute("UPDATE notifications SET created_at = ?", (teraz,))


def test_poczta_wylaczona_bez_hosta(monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "")
    assert not poczta.wlaczona()


def test_pusta_kolejka_nie_laczy_sie_z_serwerem(app, smtp):
    serwer = smtp()
    assert wyslij(app) == (0, 0)
    assert serwer.zdarzenia == []


def test_wysylka_kolejki(app, smtp):
    serwer = smtp()
    eskaluj(app, CHWILE_PO)
    ustaw_czas_powiadomien(CHWILE_PO)

    assert wyslij(app) == (3, 0)
    assert [z[0] for z in serwer.zdarzenia] == ["polaczenie", "starttls", "quit"]
    msg = serwer.wyslane[0]
    assert msg["To"] == "m.lewandowski@firma.pl"
    assert msg["Subject"].startswith("[HelpDesk] Przekroczony termin SLA")
    assert "Marek Lewandowski" in msg.get_content()
    assert stan_kolejki() == [(3, 1, 0)] * 3
    # Wysłane nie idą drugi raz.
    assert wyslij(app) == (0, 0)


def test_link_do_zgloszenia_gdy_znany_adres_aplikacji(app, smtp, monkeypatch):
    monkeypatch.setattr(config, "APP_URL", "https://helpdesk.firma.pl")
    serwer = smtp()
    eskaluj(app, CHWILE_PO)
    ustaw_czas_powiadomien(CHWILE_PO)
    wyslij(app)
    assert "https://helpdesk.firma.pl/#zgloszenie-1" in serwer.wyslane[0].get_content()


def test_ssl_i_logowanie(app, smtp, monkeypatch):
    monkeypatch.setattr(config, "SMTP_TLS", "ssl")
    monkeypatch.setattr(config, "SMTP_USER", "helpdesk")
    serwer = smtp()
    eskaluj(app, CHWILE_PO)
    ustaw_czas_powiadomien(CHWILE_PO)
    wyslij(app)
    assert serwer.zdarzenia[0] == ("polaczenie", "smtp.test", 587, True)
    assert ("login", "helpdesk") in serwer.zdarzenia
    assert ("starttls",) not in serwer.zdarzenia


def test_bez_szyfrowania(app, smtp, monkeypatch):
    monkeypatch.setattr(config, "SMTP_TLS", "brak")
    serwer = smtp()
    eskaluj(app, CHWILE_PO)
    ustaw_czas_powiadomien(CHWILE_PO)
    wyslij(app)
    assert ("starttls",) not in serwer.zdarzenia and serwer.wyslane


def test_odrzucony_adres_traci_probe_a_reszta_idzie(app, smtp):
    serwer = smtp(odrzuc={"admin@firma.pl"}, blad_quit=True)
    eskaluj(app, POL_GODZINY_PO)                 # 1 x admin + 3 x technik
    ustaw_czas_powiadomien(POL_GODZINY_PO)
    assert wyslij(app, POL_GODZINY_PO) == (3, 1)
    assert (4, 0, 1) in stan_kolejki()


def test_niedostepny_serwer_zuzywa_probe_kazdej_wiadomosci(app, smtp):
    smtp(blad_polaczenia=True)
    eskaluj(app, CHWILE_PO)
    ustaw_czas_powiadomien(CHWILE_PO)
    assert wyslij(app) == (0, 3)
    assert stan_kolejki() == [(3, 0, 1)] * 3


def test_po_wyczerpaniu_prob_wiadomosc_nie_jest_ponawiana(app, smtp):
    serwer = smtp()
    eskaluj(app, CHWILE_PO)
    ustaw_czas_powiadomien(CHWILE_PO)
    with baza() as conn:
        conn.execute("UPDATE notifications SET email_proby = ?", (config.EMAIL_MAX_PROB,))
    assert wyslij(app) == (0, 0) and serwer.zdarzenia == []


def test_stare_powiadomienia_nie_ida_mailem(app, smtp):
    """Po włączeniu SMTP po czasie użytkownik nie dostaje lawiny starych wiadomości."""
    serwer = smtp()
    eskaluj(app, CHWILE_PO)
    ustaw_czas_powiadomien(CHWILE_PO)
    assert wyslij(app, "2026-01-02 00:10:01") == (0, 0)
    assert serwer.zdarzenia == []


def test_uzytkownik_bez_adresu_nie_trafia_do_kolejki(app, smtp):
    smtp()
    with baza() as conn:
        conn.execute("UPDATE users SET email = '' WHERE id = 3")
    eskaluj(app, CHWILE_PO)
    ustaw_czas_powiadomien(CHWILE_PO)
    assert wyslij(app) == (0, 0)


# ---------------------------------------------------------------
# Proces roboczy
# ---------------------------------------------------------------

def test_przebieg_eskaluje_wysyla_i_zostawia_znacznik(app, smtp, monkeypatch, tmp_path):
    serwer = smtp()
    znacznik = tmp_path / "heartbeat"
    monkeypatch.setattr(config, "WORKER_HEARTBEAT", str(znacznik))

    worker.przebieg(app)   # „teraz” = bieżący czas, a terminy w danych minęły

    assert stopnie()[1] == 2 and znacznik.exists()
    assert len(serwer.wyslane) == 6


def test_blad_jednego_zadania_nie_zatrzymuje_drugiego(app, smtp, monkeypatch, caplog):
    serwer = smtp()
    monkeypatch.setattr(eskalacja, "eskaluj", lambda: 1 / 0)
    with baza() as conn:
        conn.execute("INSERT INTO notifications (user_id, ticket_id, typ, tresc)"
                     " VALUES (3, 1, 'status', 'test')")
    worker.przebieg(app)
    assert "Eskalacja SLA nie powiodla sie" in caplog.text
    assert len(serwer.wyslane) == 1

    monkeypatch.setattr(poczta, "wyslij_zalegle", lambda: 1 / 0)
    worker.przebieg(app)
    assert "Wysylka e-maili nie powiodla sie" in caplog.text


def test_bez_smtp_przebieg_tylko_eskaluje(app, monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "")
    monkeypatch.setattr(config, "WORKER_HEARTBEAT", "")
    monkeypatch.setattr(poczta, "wyslij_zalegle", lambda: pytest.fail("poczta wylaczona"))
    worker.przebieg(app)
    assert stopnie()[1] == 2


def test_petla_konczy_sie_po_sygnale_stop(app, monkeypatch):
    przebiegi = []
    stop = threading.Event()

    def przebieg(_app):
        przebiegi.append(1)
        if len(przebiegi) == 2:
            stop.set()

    monkeypatch.setattr(worker, "przebieg", przebieg)
    worker.petla(app, stop, interwal=0)
    assert len(przebiegi) == 2


def test_main_uruchamia_petle_i_rejestruje_obsluge_sygnalow(monkeypatch):
    import signal
    zarejestrowane = {}
    monkeypatch.setattr(signal, "signal", lambda s, f: zarejestrowane.setdefault(s, f))
    monkeypatch.setattr(worker, "create_app", lambda: "aplikacja")

    def petla(app, stop, interwal):
        assert app == "aplikacja" and interwal == config.WORKER_INTERWAL
        zarejestrowane[signal.SIGTERM]()      # docker stop
        assert stop.is_set()

    monkeypatch.setattr(worker, "petla", petla)
    worker.main()
    assert signal.SIGINT in zarejestrowane


# ---------------------------------------------------------------
# Migracja istniejącej bazy
# ---------------------------------------------------------------

def test_starsza_baza_dostaje_kolumne_eskalacji(tmp_path, monkeypatch):
    sciezka = tmp_path / "stara.db"
    monkeypatch.setattr(config, "DB_PATH", str(sciezka))
    database.init_db()
    # Baza sprzed tej zmiany: bez kolumny, z istniejącym zgłoszeniem.
    with sqlite3.connect(sciezka) as conn:
        conn.execute("ALTER TABLE tickets DROP COLUMN eskalacja")
        conn.execute("INSERT INTO users (id, username, password, name, role)"
                     " VALUES (1, 'u', 'x', 'U', 'pracownik')")
        conn.execute("INSERT INTO tickets (title, description, created_by) VALUES ('t', 'o', 1)")

    database.init_db()
    with sqlite3.connect(sciezka) as conn:
        assert conn.execute("SELECT eskalacja FROM tickets").fetchone() == (0,)
