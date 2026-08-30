"""Wspolne fixtures dla testow.

Kazdy test dostaje wlasna, swieza baze SQLite w katalogu tymczasowym —
testy sa od siebie niezalezne i nie dotykaja bazy deweloperskiej.
"""

import os
import shutil
import sqlite3
import sys

import pytest

# SECRET_KEY musi byc ustawiony ZANIM zaimportujemy auth.py — modul czyta
# go w momencie importu.
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")

# Katalog glowny projektu na sciezce importow (testy leza w tests/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash  # noqa: E402

from app import config as db_module
from app.data import database  # noqa: E402
from app import create_app  # noqa: E402
from app.extensions import limiter  # noqa: E402


# Uzytkownicy testowi: (id, login, haslo, imie, rola)
USERS = [
    (1, "k.nowak",       "haslo123", "Katarzyna Nowak",   "pracownik"),
    (2, "p.wisniewski",  "haslo123", "Piotr Wisniewski",  "pracownik"),
    (3, "m.lewandowski", "tech123",  "Marek Lewandowski", "technik"),
    (4, "admin",         "admin123", "Tomasz Adamski",    "admin"),
]

# (id, tytul, status, priorytet, kategoria, autor, przypisany)
TICKETS = [
    (1, "Podejrzany e-mail",      "Nowe",      "Krytyczny", "Bezpieczenstwo", 1, None),
    (2, "Nie dziala VPN",         "W trakcie", "Sredni",    "Siec",           1, 3),
    (3, "Wymiana klawiatury",     "Nowe",      "Niski",     "Peryferia",      2, None),
    (4, "Reset hasla",            "Zamkniete", "Wysoki",    "Konta i dostep", 2, 3),
]


# Hashowanie scrypt jest celowo kosztowne. Liczymy je RAZ na caly przebieg
# testow zamiast dla kazdego testu osobno — inaczej sam seed dominuje czas.
_HASHE = {password: generate_password_hash(password) for _, _, password, _, _ in USERS}


def _seed(path):
    """Minimalny, przewidywalny zestaw danych — niezalezny od seed.py."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")

    for uid, username, password, name, role in USERS:
        conn.execute(
            "INSERT INTO users (id, username, password, name, role, email) VALUES (?,?,?,?,?,?)",
            (uid, username, _HASHE[password], name, role, f"{username}@firma.pl"),
        )

    for tid, title, status, priority, category, created_by, assigned_to in TICKETS:
        conn.execute(
            """INSERT INTO tickets
               (id, title, description, category, priority, status, created_by,
                assigned_to, ai_categorized, sla_deadline)
               VALUES (?,?,?,?,?,?,?,?,1,'2026-01-01T00:00:00')""",
            (tid, title, f"Opis: {title}", category, priority, status, created_by, assigned_to),
        )

    # Notatka wewnetrzna na zgloszeniu #1 — sluzy do sprawdzenia, czy
    # pracownik jej NIE widzi.
    conn.execute(
        "INSERT INTO notes (ticket_id, author_id, content, internal) VALUES (?,?,?,1)",
        (1, 3, "Notatka wewnetrzna technika"),
    )
    conn.execute(
        "INSERT INTO notes (ticket_id, author_id, content, internal) VALUES (?,?,?,0)",
        (1, 3, "Notatka widoczna dla zglaszajacego"),
    )

    conn.commit()
    conn.close()


@pytest.fixture(scope="session")
def wzorzec_bazy(tmp_path_factory):
    """Gotowa baza (schemat + indeksy + dane) budowana RAZ na cala sesje.

    Tworzenie tabel i indeksow dla kazdego z ponad dwustu testow osobno
    wyraznie wydluzalo przebieg. Skopiowanie gotowego pliku daje ten sam
    efekt — kazdy test nadal dostaje wlasna, nietkniela baze.
    """
    sciezka = tmp_path_factory.mktemp("wzorzec") / "wzorzec.db"

    poprzednia = db_module.DB_PATH
    db_module.DB_PATH = str(sciezka)
    try:
        database.init_db()
        _seed(str(sciezka))
    finally:
        db_module.DB_PATH = poprzednia

    return sciezka


def ustaw_limiter(wlaczony: bool):
    """Wlacza lub wylacza ograniczanie zadan na czas testu.

    Uzywamy atrybutu `limiter.enabled`, a NIE ustawienia RATELIMIT_ENABLED
    w konfiguracji Flaska. Flask-Limiter 4.x usunal ten klucz — ustawienie go
    przestalo cokolwiek robic i zaden blad sie nie pojawil. Skutek byl
    podstepny: limity dzialaly w trakcie calego przebiegu testow, kolejne
    logowania zuzywaly pule 5/min na konto, a testy uruchamiane pozniej
    dostawaly 429 i wywracaly sie na brakujacych polach odpowiedzi.
    Pojedynczo przechodzily, bo licznik byl wtedy pusty.
    """
    limiter.enabled = wlaczony
    try:
        limiter.reset()
    except Exception:  # pragma: no cover — zalezy od backendu magazynu
        pass


@pytest.fixture
def app(tmp_path, monkeypatch, wzorzec_bazy):
    """Aplikacja Flask ze swieza baza. Limiter wylaczony — wlacza go osobny test."""
    db_file = tmp_path / "test_helpdesk.db"
    shutil.copyfile(wzorzec_bazy, db_file)
    monkeypatch.setattr(db_module, "DB_PATH", str(db_file))

    application = create_app()
    application.config.update(TESTING=True)
    ustaw_limiter(False)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _naglowek_dla(uzytkownik_id):
    """Token wystawiony wprost, bez przechodzenia przez logowanie HTTP.

    Wiekszosc testow potrzebuje po prostu tozsamosci, a nie sprawdzenia
    logowania — to ostatnie ma wlasny, dokladny zestaw w `test_api_auth.py`.

    Logowanie przez HTTP w kazdym z ponad trzystu testow miало dwa skutki
    uboczne: kazdy test placil za kosztowne hashowanie scrypt, a caly przebieg
    byl sprzezony ze wspoldzielonym licznikiem limitu zadan. Gdy limit bywal
    aktywny, testy z konca przebiegu dostawaly 429 i wywracaly sie w losowych
    miejscach.
    """
    from app.security.tokens import generate_token
    return auth_header(generate_token(uzytkownik_id))


@pytest.fixture
def pracownik(client):
    """Token pracownika o id=1 (Katarzyna Nowak)."""
    return _naglowek_dla(1)


@pytest.fixture
def pracownik2(client):
    """Token drugiego pracownika o id=2 — do testow izolacji danych."""
    return _naglowek_dla(2)


@pytest.fixture
def technik(client):
    """Token technika o id=3 (Marek Lewandowski)."""
    return _naglowek_dla(3)


@pytest.fixture
def rate_limited_client(app):
    """Klient z WLACZONYM ograniczaniem zadan i wyzerowanym licznikiem."""
    ustaw_limiter(True)
    yield app.test_client()
    # Wylaczenie i wyzerowanie po tescie — inaczej licznik zuzyty tutaj
    # wplywalby na testy uruchamiane pozniej.
    ustaw_limiter(False)
