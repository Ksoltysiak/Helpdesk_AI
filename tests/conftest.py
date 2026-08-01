"""Wspolne fixtures dla testow.

Kazdy test dostaje wlasna, swieza baze SQLite w katalogu tymczasowym —
testy sa od siebie niezalezne i nie dotykaja bazy deweloperskiej.
"""

import os
import sys
import sqlite3

import pytest

# SECRET_KEY musi byc ustawiony ZANIM zaimportujemy auth.py — modul czyta
# go w momencie importu.
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")

# Katalog glowny projektu na sciezce importow (testy leza w tests/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash  # noqa: E402

import db as db_module  # noqa: E402
from app import create_app  # noqa: E402
from rate_limit import limiter  # noqa: E402


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


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Aplikacja Flask ze swieza baza. Limiter wylaczony — wlacza go osobny test."""
    db_file = tmp_path / "test_helpdesk.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_file))

    db_module.init_db()
    _seed(str(db_file))

    application = create_app()
    application.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Logowanie {username} nie powiodlo sie: {resp.get_json()}"
    return resp.get_json()["token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pracownik(client):
    """Token pracownika o id=1 (Katarzyna Nowak)."""
    return auth_header(_login(client, "k.nowak", "haslo123"))


@pytest.fixture
def pracownik2(client):
    """Token drugiego pracownika o id=2 — do testow izolacji danych."""
    return auth_header(_login(client, "p.wisniewski", "haslo123"))


@pytest.fixture
def technik(client):
    """Token technika o id=3 (Marek Lewandowski)."""
    return auth_header(_login(client, "m.lewandowski", "tech123"))


@pytest.fixture
def rate_limited_client(app):
    """Klient z WLACZONYM ograniczaniem zadan i wyzerowanym licznikiem."""
    app.config["RATELIMIT_ENABLED"] = True
    try:
        limiter.reset()
    except Exception:  # pragma: no cover — zalezy od backendu magazynu
        pass
    yield app.test_client()
    app.config["RATELIMIT_ENABLED"] = False
    try:
        limiter.reset()
    except Exception:  # pragma: no cover
        pass
