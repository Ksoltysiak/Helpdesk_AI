"""Połączenie z bazą, schemat, indeksy i migracje.

Ścieżka do pliku bazy czytana jest z `config.DB_PATH` **w momencie użycia**,
a nie importu — dzięki temu testy mogą wskazać własną bazę bez przeładowywania
modułu.
"""

import sqlite3

from flask import g

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT UNIQUE NOT NULL,
    password  TEXT NOT NULL,
    name      TEXT NOT NULL,
    role      TEXT NOT NULL CHECK(role IN ('pracownik','technik','admin')),
    email     TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    category        TEXT,
    priority        TEXT,
    status          TEXT NOT NULL DEFAULT 'Nowe',
    created_by      INTEGER NOT NULL REFERENCES users(id),
    assigned_to     INTEGER REFERENCES users(id),
    ai_categorized  INTEGER DEFAULT 0,
    ai_pewnosc      REAL,
    sla_deadline    TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    closed_at       TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    author_id   INTEGER NOT NULL REFERENCES users(id),
    content     TEXT NOT NULL,
    internal    INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    user_id     INTEGER REFERENCES users(id),
    action      TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    timestamp   TEXT DEFAULT (datetime('now'))
);
"""

INDEKSY = """
-- Bez indeksow kazde filtrowanie i kazdy licznik na pulpicie oznacza
-- przeszukanie calej tabeli zgloszen.
CREATE INDEX IF NOT EXISTS idx_tickets_created_by  ON tickets(created_by);
CREATE INDEX IF NOT EXISTS idx_tickets_status      ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_priority    ON tickets(priority);
CREATE INDEX IF NOT EXISTS idx_tickets_category    ON tickets(category);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned_to ON tickets(assigned_to);

-- Filtry laczone (np. status + priorytet) oraz lista pracownika, ktora
-- zawsze sortuje malejaco po identyfikatorze.
CREATE INDEX IF NOT EXISTS idx_tickets_status_priority ON tickets(status, priority);
CREATE INDEX IF NOT EXISTS idx_tickets_autor_id        ON tickets(created_by, id DESC);

-- Pobieranie notatek i historii konkretnego zgloszenia.
CREATE INDEX IF NOT EXISTS idx_notes_ticket     ON notes(ticket_id);
CREATE INDEX IF NOT EXISTS idx_audit_ticket     ON audit_log(ticket_id);
"""

# Ustawienia obowiazujace dla KAZDEGO polaczenia — nie sa zapisywane w pliku
# bazy, wiec trzeba je ustawiac za kazdym razem. Sa tanie (operacje w pamieci).
PRAGMY_POLACZENIA = (
    ("foreign_keys", "ON"),
    ("synchronous", "NORMAL"),   # bezpieczne przy WAL, znacznie szybsze od FULL
    ("busy_timeout", "5000"),    # czekaj na zwolnienie blokady zamiast zglaszac blad
    ("cache_size", "-8000"),     # ok. 8 MB cache stron na polaczenie
)

# Tryb dziennika jest zapisany w naglowku pliku bazy — ustawiany RAZ, przy
# inicjalizacji. Powtarzanie go przy kazdym zadaniu oznaczaloby zbedna operacje
# dyskowa na sciezce kazdego zapytania.
#
# WAL pozwala czytac w trakcie zapisu; bez niego jeden zapis blokuje wszystkie
# odczyty, co przy kilku procesach gunicorna konczy sie bledem
# "database is locked".
PRAGMA_TRWALA = ("journal_mode", "WAL")

# Kolumny dodane po pierwszym wdrozeniu. CREATE TABLE IF NOT EXISTS nie zmienia
# istniejacej tabeli, wiec baze z wczesniejszej wersji trzeba uzupelnic wprost.
MIGRACJE = (
    ("tickets", "ai_pewnosc", "REAL"),
)


def _zastosuj_pragmy(conn):
    for nazwa, wartosc in PRAGMY_POLACZENIA:
        conn.execute(f"PRAGMA {nazwa} = {wartosc}")


def _domigruj(conn):
    for tabela, kolumna, typ in MIGRACJE:
        istniejace = {w[1] for w in conn.execute(f"PRAGMA table_info({tabela})")}
        if kolumna not in istniejace:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {kolumna} {typ}")


def get_db():
    """Połączenie na czas jednego żądania."""
    if "db" not in g:
        g.db = sqlite3.connect(config.DB_PATH)
        g.db.row_factory = sqlite3.Row
        _zastosuj_pragmy(g.db)
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def sprawdz_polaczenie() -> bool:
    """Czy baza odpowiada — na potrzeby kontroli zdrowia.

    Najtańsze możliwe zapytanie: potwierdza, że plik jest osiągalny i że
    połączenie da się otworzyć, bez dotykania danych.
    """
    try:
        get_db().execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


def init_db():
    """Tworzy brakujace tabele, kolumny i indeksy.

    Bezpieczne do wielokrotnego wywolania — uruchamiane przy kazdym starcie
    kontenera, wiec istniejaca baza dostaje zmiany schematu bez osobnego kroku.
    """
    conn = sqlite3.connect(config.DB_PATH)
    _zastosuj_pragmy(conn)
    nazwa, wartosc = PRAGMA_TRWALA
    conn.execute(f"PRAGMA {nazwa} = {wartosc}")
    conn.executescript(SCHEMA)
    _domigruj(conn)
    conn.executescript(INDEKSY)
    conn.commit()
    conn.close()
