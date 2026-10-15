"""Połączenie z bazą, schemat, indeksy i migracje.

Ścieżka do pliku bazy czytana jest z `config.DB_PATH` **w momencie użycia**,
a nie importu — dzięki temu testy mogą wskazać własną bazę bez przeładowywania
modułu.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from flask import g

from app import config

# Definicja tabeli uzytkownikow — wspolna dla schematu i migracji, ktora
# przebudowuje te tabele (patrz _migracja_1_kierownik).
KOLUMNY_USERS = """
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT UNIQUE NOT NULL,
    password  TEXT NOT NULL,
    name      TEXT NOT NULL,
    role      TEXT NOT NULL CHECK(role IN ('pracownik','technik','kierownik')),
    email     TEXT,
    client_id INTEGER REFERENCES clients(id)
"""

SCHEMA = f"""
-- Firmy obslugiwane przez helpdesk. Pracownik zglaszajacy awarie nalezy do
-- jednej z nich (users.client_id). Technicy i kierownik sa personelem
-- helpdesku — firmy, ktore obsluguja, opisuje tabela technician_clients.
CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users ({KOLUMNY_USERS});

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
    closed_at       TEXT,
    -- Klient zapisany w chwili utworzenia zgloszenia, a nie wyliczany z autora:
    -- gdy pracownik zmieni firme, jego dawne zgloszenia nadal naleza do
    -- poprzedniej — inaczej raporty dla klientow zmienialyby sie wstecz.
    client_id       INTEGER REFERENCES clients(id)
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

-- Firmy obslugiwane przez technika. Technik tworzy raporty tylko dla nich;
-- kierownik — dla wszystkich firm, wiec nie potrzebuje wpisow.
CREATE TABLE IF NOT EXISTS technician_clients (
    technician_id INTEGER NOT NULL REFERENCES users(id),
    client_id     INTEGER NOT NULL REFERENCES clients(id),
    PRIMARY KEY (technician_id, client_id)
);

-- Czasy SLA zmienione przez kierownika. Brak wiersza oznacza wartosc
-- domyslna z app/domain/ai.py — swieza baza dziala bez osobnego kroku.
CREATE TABLE IF NOT EXISTS sla_settings (
    priority    TEXT PRIMARY KEY,
    hours       INTEGER NOT NULL CHECK(hours BETWEEN 1 AND 720),
    updated_by  INTEGER REFERENCES users(id),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- Historia zmian ustawien: kto, co i kiedy zmienil. Dziennik audytu
-- zgloszen sie tu nie nadaje — kazdy jego wpis dotyczy jednego zgloszenia.
CREATE TABLE IF NOT EXISTS settings_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),
    setting     TEXT NOT NULL,
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

-- Otwarte zgloszenia: obciazenie technikow, kolejka kierownika i zgloszenia
-- zagrozone SLA. Indeks pokrywa wszystkie trzy zapytania — czytaja tylko
-- otwarte zgloszenia, a nie cala historie przypisan.
CREATE INDEX IF NOT EXISTS idx_tickets_otwarte ON tickets(status, sla_deadline, assigned_to);
-- To samo dla jednego technika: jego otwarte zgloszenia, bez przegladania
-- calej historii zgloszen, ktore kiedykolwiek prowadzil.
CREATE INDEX IF NOT EXISTS idx_tickets_opiekun_otwarte
    ON tickets(assigned_to, status, sla_deadline);

-- Lista zgloszen jednego klienta (filtr technika), sortowana jak kazda lista.
CREATE INDEX IF NOT EXISTS idx_tickets_klient_id       ON tickets(client_id, id DESC);

-- Raporty wybieraja zgloszenia z okresu — jednego klienta albo wszystkich.
-- Indeksy POKRYWAJA kolumny uzywane w raporcie: przy okresie obejmujacym duza
-- czesc tabeli odczyt wiersz po wierszu przez indeks bylby wolniejszy niz
-- przegladanie calej tabeli, a tak raport czyta tylko waski indeks, bez
-- siegania do wierszy z dlugimi opisami zgloszen.
CREATE INDEX IF NOT EXISTS idx_tickets_klient_raport ON tickets(
    client_id, created_at, category, priority, status, sla_deadline, closed_at);
CREATE INDEX IF NOT EXISTS idx_tickets_raport ON tickets(
    created_at, category, priority, status, sla_deadline, closed_at);

-- Pobieranie notatek i historii konkretnego zgloszenia.
CREATE INDEX IF NOT EXISTS idx_notes_ticket     ON notes(ticket_id);
CREATE INDEX IF NOT EXISTS idx_audit_ticket     ON audit_log(ticket_id);

-- Statystyki skutecznosci AI licza korekty po rodzaju akcji. Dziennik audytu
-- rosnie najszybciej (kilka wpisow na zgloszenie), a bez indeksu kazde
-- otwarcie zestawienia przeszukiwaloby go w calosci.
CREATE INDEX IF NOT EXISTS idx_audit_akcja      ON audit_log(action, ticket_id);

-- Chwila rozwiazania zgloszenia (raporty: czas obslugi i dotrzymanie SLA).
-- Indeks czesciowy obejmuje tylko wpisy „-> Rozwiazane" — jest maly, a raport
-- odczytuje z niego MAX(timestamp) bez siegania do tabeli.
CREATE INDEX IF NOT EXISTS idx_audit_rozwiazanie ON audit_log(ticket_id, timestamp)
    WHERE action = 'Zmiana statusu' AND new_value = 'Rozwiazane';

-- Statystyki technikow wybieraja zmiany statusu z OKRESU (rozwiazania
-- i podjecia), a nie wpisy jednego zgloszenia. Indeksy czesciowe — kazdy
-- obejmuje jeden rodzaj zmiany, wiec sa male i nie konkuruja z indeksem
-- powyzej przy odczycie historii pojedynczego zgloszenia.
CREATE INDEX IF NOT EXISTS idx_audit_rozwiazania_w_czasie
    ON audit_log(timestamp, user_id, ticket_id)
    WHERE action = 'Zmiana statusu' AND new_value = 'Rozwiazane';
CREATE INDEX IF NOT EXISTS idx_audit_podjecia_w_czasie
    ON audit_log(timestamp, user_id, ticket_id)
    WHERE action = 'Zmiana statusu' AND old_value = 'Nowe' AND new_value = 'W trakcie';
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
    ("users",   "client_id",  "INTEGER REFERENCES clients(id)"),
    ("tickets", "client_id",  "INTEGER REFERENCES clients(id)"),
)

# Uzupelnienie danych po migracji. Zgloszenia sprzed wprowadzenia klientow
# dziedzicza firme autora. Warunek `client_id IS NULL` sprawia, ze ponowne
# uruchomienie niczego nie nadpisuje.
UZUPELNIENIA = (
    """UPDATE tickets SET client_id =
           (SELECT client_id FROM users WHERE users.id = tickets.created_by)
       WHERE client_id IS NULL""",
)


def czas_utc(wartosc):
    """Znacznik czasu z bazy -> ISO 8601 z jawną strefą UTC.

    `datetime('now')` w SQLite zapisuje czas UTC, ale bez oznaczenia strefy
    („2026-07-25 11:40:00"). Przeglądarka czyta taki napis jako czas
    LOKALNY, więc użytkownik w Polsce widział godziny przesunięte o 1–2 h,
    a część przeglądarek nie umie go w ogóle sparsować przez spację.
    """
    if not wartosc:
        return wartosc
    return wartosc.replace(" ", "T") + ("" if wartosc.endswith("Z") else "Z")


def teraz_utc(przesuniecie=None):
    """Bieżący czas UTC w formacie, w jakim zapisuje go SQLite."""
    chwila = datetime.now(timezone.utc)
    if przesuniecie is not None:
        chwila += przesuniecie
    return chwila.strftime("%Y-%m-%d %H:%M:%S")


def godziny_miedzy(poczatek, koniec):
    """Wyrażenie SQL: liczba godzin między dwoma znacznikami czasu.

    Liczone z pełnych sekund. `julianday()` mierzy czas w ułamkach doby,
    przez co 45 minut wychodziło jako 0,7499… h i po zaokrągleniu jako 0,7.
    `strftime('%s')` rozumie oba zapisy dat w bazie.
    """
    return (f"((CAST(strftime('%s', {koniec}) AS INTEGER)"
            f" - CAST(strftime('%s', {poczatek}) AS INTEGER)) / 3600.0)")


def granice_dob(od, do):
    """Okres [od, do] (daty włącznie) jako napisy do porównań w SQL.

    Pełne doby UTC: od `od` 00:00:00 włącznie do dnia po `do` 00:00:00
    wyłącznie. Porównanie tekstowe z granicą o północy działa poprawnie dla
    obu zapisów dat w bazie (`2026-10-01 10:00:00` i `2026-10-01T10:00:00`).
    """
    return (f"{od.isoformat()} 00:00:00",
            f"{(do + timedelta(days=1)).isoformat()} 00:00:00")


def _migracja_1_kierownik(conn):
    """Rola `admin` zastąpiona rolą `kierownik`.

    Lista ról jest warunkiem CHECK w definicji tabeli, a SQLite nie pozwala
    zmienić go w miejscu. Tabelę trzeba przebudować według procedury
    z dokumentacji SQLite: nowa tabela, kopia danych, podmiana nazw. Klucze
    obce są na ten czas wyłączone, bo usuwaną tabelę wskazują zgłoszenia,
    notatki i audyt — po podmianie wskazują nową tabelę o tej samej nazwie.
    """
    sekwencja = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'users'").fetchone()
    # Naruszenia, które były w bazie już wcześniej (np. z czasu, gdy klucze
    # obce nie były egzekwowane), nie są winą migracji i nie mogą blokować
    # startu aplikacji. Przerywamy tylko wtedy, gdy przebudowa dodała nowe.
    naruszenia_przed = set(conn.execute("PRAGMA foreign_key_check").fetchall())
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript(f"""
            BEGIN;
            CREATE TABLE users_nowa ({KOLUMNY_USERS});
            INSERT INTO users_nowa (id, username, password, name, role, email, client_id)
                SELECT id, username, password, name,
                       CASE role WHEN 'admin' THEN 'kierownik' ELSE role END,
                       email, client_id
                FROM users;
            DROP TABLE users;
            ALTER TABLE users_nowa RENAME TO users;
        """)
        # Identyfikatory usuniętych kont nie mogą wrócić do obiegu — historia
        # zgłoszeń przypisałaby je wtedy komuś innemu.
        if sekwencja:
            conn.execute("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'users'",
                         (sekwencja[0],))
        # Zabezpieczenie na przyszłe zmiany tej migracji: obecna kopiuje
        # wszystkie wiersze z tymi samymi identyfikatorami, więc nie może
        # zostawić osieroconych odwołań — i nie da się tego wywołać w teście.
        if set(conn.execute("PRAGMA foreign_key_check").fetchall()) - naruszenia_przed:
            raise sqlite3.IntegrityError(  # pragma: no cover
                "Przebudowa tabeli users naruszyła klucze obce")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


# Zmiany, których nie da się wyrazić przez CREATE ... IF NOT EXISTS ani
# ADD COLUMN. Każda wykonuje się dokładnie raz, w kolejności; numer ostatniej
# zapisany jest w nagłówku pliku bazy (PRAGMA user_version).
MIGRACJE_WERSJI = (
    _migracja_1_kierownik,
)


def _wykonaj_migracje_wersji(conn, nowa_baza):
    wersja = conn.execute("PRAGMA user_version").fetchone()[0]
    if nowa_baza:
        # Schemat właśnie powstał w aktualnej postaci — nie ma czego migrować.
        wersja = len(MIGRACJE_WERSJI)
    for numer in range(wersja + 1, len(MIGRACJE_WERSJI) + 1):
        MIGRACJE_WERSJI[numer - 1](conn)
        conn.execute(f"PRAGMA user_version = {numer}")
        wersja = numer
    if nowa_baza:
        conn.execute(f"PRAGMA user_version = {wersja}")


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

    Samo `SELECT 1` nie czyta pliku bazy, więc przechodziło nawet wtedy, gdy
    bazy nie było: SQLite tworzy w jej miejscu pusty plik. Odwołanie do
    tabeli wymaga odczytu schematu i jednej strony danych, a nadal jest tanie.
    """
    try:
        get_db().execute("SELECT 1 FROM tickets LIMIT 1").fetchone()
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
    nowa_baza = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone() is None
    conn.executescript(SCHEMA)
    _domigruj(conn)
    _wykonaj_migracje_wersji(conn, nowa_baza)
    for zapytanie in UZUPELNIENIA:
        conn.execute(zapytanie)
    conn.executescript(INDEKSY)
    conn.commit()
    conn.close()
