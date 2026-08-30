"""Testy zabezpieczen zaleznych od srodowiska wdrozenia:
wymuszanie HTTPS, HSTS, zaufanie do odwrotnego proxy oraz sila klucza
podpisujacego.

Wszystkie te mechanizmy sa wlaczane zmiennymi srodowiskowymi, wiec kazdy
test buduje wlasna instancje aplikacji z odpowiednia konfiguracja.
"""

import os
import subprocess
import sys

import pytest

from app.data import database
from conftest import ustaw_limiter

pytestmark = pytest.mark.integration

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def app_z_ustawieniami(tmp_path, monkeypatch):
    """Fabryka aplikacji z wybranymi ustawieniami wdrozeniowymi.

    Ustawienia podmieniamy WPROST na atrybutach `config`, bez przeladowywania
    modulow. Wczesniejsza wersja robila `importlib.reload(app.config)`
    i `reload(app)`, co nadpisywalo stan wspoldzielony z pozostalymi testami
    (m.in. DB_PATH i instancje limitera). Skutkiem byly bledy pojawiajace sie
    losowo w zupelnie innych testach — zaleznie od kolejnosci wykonania.

    Podmiana atrybutow wystarcza, bo aplikacja czyta TRUST_PROXY w chwili
    tworzenia, a FORCE_HTTPS przy kazdym zadaniu.
    """
    from app import config as config_module

    def zbuduj(**ustawienia):
        for klucz, wartosc in ustawienia.items():
            monkeypatch.setattr(config_module, klucz, wartosc)

        db_file = tmp_path / f"cfg_{abs(hash(frozenset(ustawienia.items())))}.db"
        monkeypatch.setattr(config_module, "DB_PATH", str(db_file))
        database.init_db()

        from app import create_app
        aplikacja = create_app()
        aplikacja.config.update(TESTING=True)
        ustaw_limiter(False)
        return aplikacja

    return zbuduj


# ---------------------------------------------------------------
# Wymuszanie HTTPS
# ---------------------------------------------------------------

def test_domyslnie_http_dziala(client):
    """Bez FORCE_HTTPS lokalne uruchomienie po HTTP musi dzialac."""
    assert client.get("/").status_code == 200


def test_z_wlaczonym_force_https_nastepuje_przekierowanie(app_z_ustawieniami):
    klient = app_z_ustawieniami(FORCE_HTTPS=True).test_client()
    resp = klient.get("/", base_url="http://localhost")
    assert resp.status_code == 308
    assert resp.headers["Location"].startswith("https://")


def test_przekierowanie_zachowuje_sciezke(app_z_ustawieniami):
    klient = app_z_ustawieniami(FORCE_HTTPS=True).test_client()
    resp = klient.get("/api/tickets", base_url="http://localhost")
    assert resp.headers["Location"] == "https://localhost/api/tickets"


def test_zadanie_po_https_nie_jest_przekierowywane(app_z_ustawieniami):
    klient = app_z_ustawieniami(FORCE_HTTPS=True).test_client()
    assert klient.get("/", base_url="https://localhost").status_code == 200


# ---------------------------------------------------------------
# HSTS
# ---------------------------------------------------------------

def test_bez_https_nie_wysylamy_hsts(client):
    """HSTS po HTTP jest ignorowany, a lokalnie potrafi zablokowac dostep."""
    assert "Strict-Transport-Security" not in client.get("/").headers


def test_z_wlaczonym_https_wysylamy_hsts(app_z_ustawieniami):
    klient = app_z_ustawieniami(FORCE_HTTPS=True).test_client()
    naglowek = klient.get("/", base_url="https://localhost").headers.get("Strict-Transport-Security")
    assert naglowek is not None
    assert "max-age=31536000" in naglowek


# ---------------------------------------------------------------
# Permissions-Policy
# ---------------------------------------------------------------

def test_permissions_policy_wylacza_nieuzywane_funkcje(client):
    polityka = client.get("/").headers.get("Permissions-Policy", "")
    for funkcja in ("geolocation=()", "microphone=()", "camera=()"):
        assert funkcja in polityka


# ---------------------------------------------------------------
# Zaufanie do odwrotnego proxy
# ---------------------------------------------------------------

def test_domyslnie_naglowek_x_forwarded_for_jest_ignorowany(app_z_ustawieniami):
    """Bez zaufanego proxy podrobiony naglowek pozwolilby obchodzic limity."""
    aplikacja = app_z_ustawieniami(TRUST_PROXY=False)
    with aplikacja.test_request_context("/", headers={"X-Forwarded-For": "1.2.3.4"}):
        from flask_limiter.util import get_remote_address
        assert get_remote_address() != "1.2.3.4"


def test_po_wlaczeniu_trust_proxy_adres_klienta_jest_odczytywany(app_z_ustawieniami):
    """Za proxy bez tego wszyscy dzieliliby jeden licznik limitu logowania."""
    aplikacja = app_z_ustawieniami(TRUST_PROXY=True)

    widziany = {}

    @aplikacja.route("/_adres_testowy")
    def adres():
        from flask_limiter.util import get_remote_address
        widziany["ip"] = get_remote_address()
        return "ok"

    aplikacja.test_client().get("/_adres_testowy",
                                headers={"X-Forwarded-For": "203.0.113.9"})
    assert widziany["ip"] == "203.0.113.9"


# ---------------------------------------------------------------
# Sila klucza podpisujacego
# ---------------------------------------------------------------

def _uruchom_z_kluczem(klucz):
    srodowisko = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    srodowisko["PYTHONPATH"] = ROOT
    srodowisko["PYTHONIOENCODING"] = "utf-8"
    if klucz is not None:
        srodowisko["SECRET_KEY"] = klucz
    return subprocess.run(
        [sys.executable, "-W", "always", "-c", "from app import config"],
        capture_output=True, text=True, cwd=ROOT, env=srodowisko,
    )


# Logika wyboru klucza jest wydzielona z kodu importu, wiec kazdy przypadek
# da sie sprawdzic wprost — bez przeladowywania modulu.

@pytest.mark.parametrize("klucz,ma_ostrzegac,uzywa_domyslnego", [
    (None,         True,  True),    # brak klucza
    ("",           True,  True),    # pusty
    ("krotki",     True,  False),   # za krotki, ale wlasny
    ("a" * 31,     True,  False),   # tuz ponizej progu
    ("a" * 32,     False, False),   # dokladnie prog
    ("a" * 64,     False, False),   # z zapasem
])
def test_rozstrzyganie_klucza_podpisujacego(klucz, ma_ostrzegac, uzywa_domyslnego):
    from app.config import rozstrzygnij_klucz, KLUCZ_DOMYSLNY

    uzyty, ostrzezenie = rozstrzygnij_klucz(klucz)
    assert (ostrzezenie is not None) is ma_ostrzegac
    assert (uzyty == KLUCZ_DOMYSLNY) is uzywa_domyslnego
    if ma_ostrzegac:
        assert "SECRET_KEY" in ostrzezenie


def test_zbyt_krotki_klucz_wywoluje_ostrzezenie():
    wynik = _uruchom_z_kluczem("krotki")
    assert "SECRET_KEY" in wynik.stderr
    assert "32" in wynik.stderr


def test_klucz_o_wlasciwej_dlugosci_nie_ostrzega():
    wynik = _uruchom_z_kluczem("a" * 64)
    assert "SECRET_KEY" not in wynik.stderr


def test_klucz_o_granicznej_dlugosci_nie_ostrzega():
    wynik = _uruchom_z_kluczem("b" * 32)
    assert "SECRET_KEY" not in wynik.stderr
