import sqlite3
import os
import json
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash
from app import config
from app.data.database import init_db
from app.domain.ai import categorize, SLA_HOURS

# Fikcyjne firmy obslugiwane przez helpdesk (dane demonstracyjne).
CLIENTS = [
    "Piekarnia Złoty Kłos",
    "Biuro Rachunkowe Bilans",
    "Kancelaria Prawna Paragraf",
    "Hurtownia Budowlana Cegiełka",
    "Klinika Weterynaryjna Pazurek",
]

# username, password, name, role, email, klient (None = personel helpdesku).
# Nowi uzytkownicy dopisywani sa na KONCU listy — identyfikatory nadawane sa
# w tej kolejnosci, a TICKETS odwoluja sie do nich liczbami.
USERS = [
    ("k.nowak",       "haslo123", "Katarzyna Nowak",    "pracownik", "k.nowak@firma.pl",       "Piekarnia Złoty Kłos"),
    ("p.wisniewski",  "haslo123", "Piotr Wisniewski",   "pracownik", "p.wisniewski@firma.pl",  "Biuro Rachunkowe Bilans"),
    ("a.kowalczyk",   "haslo123", "Anna Kowalczyk",     "pracownik", "a.kowalczyk@firma.pl",   "Kancelaria Prawna Paragraf"),
    ("m.lewandowski", "tech123",  "Marek Lewandowski",  "technik",   "m.lewandowski@firma.pl", None),
    ("j.zielinska",   "tech123",  "Joanna Zielinska",   "technik",   "j.zielinska@firma.pl",   None),
    ("admin",         "admin123", "Tomasz Adamski",     "admin",     "admin@firma.pl",         None),
    ("e.kaminska",    "haslo123", "Ewa Kaminska",       "pracownik", "e.kaminska@firma.pl",    "Hurtownia Budowlana Cegiełka"),
    ("r.wojcik",      "haslo123", "Robert Wojcik",      "pracownik", "r.wojcik@firma.pl",      "Klinika Weterynaryjna Pazurek"),
]

# title, description, status, created_by, assigned_to, days_ago
TICKETS = [
    ("Nie dziala VPN", "Nie moge polaczyc sie z firmowym VPN, blad TLS handshake.", "Nowe", 1, None, 0),
    ("Brak internetu w sali konferencyjnej", "Caly pokoj nie ma dostepu do sieci od rana.", "Nowe", 2, None, 0),
    ("Drukarka nie drukuje", "Drukarka HP w sekretariacie nie przyjmuje zlecen.", "Nowe", 3, None, 0),
    ("Zapomniane haslo do poczty", "Nie pamietam hasla do skrzynki Outlook.", "Nowe", 1, None, 0),
    ("Podejrzany e-mail", "Dostalem maila z prosba o podanie hasla, wyglada na phishing.", "Nowe", 2, None, 0),
    ("Laptop sie przegrzewa", "Sluzbowy laptop wylacza sie po 30 minutach pracy.", "Nowe", 3, None, 1),
    ("Excel zawiesza sie przy duzych plikach", "Arkusz powyzej 40MB powoduje zawieszenie programu.", "Nowe", 1, None, 1),
    ("Myszka nie dziala", "Bezprzewodowa myszka nie reaguje mimo nowych baterii.", "Nowe", 2, None, 1),

    ("Serwer plikow nie odpowiada", "Dysk sieciowy Z: jest niedostepny dla calego dzialu.", "W trakcie", 3, 4, 1),
    ("Komputer wyswietla niebieski ekran", "BSOD i restart co kilka godzin.", "W trakcie", 1, 4, 2),
    ("Konto zablokowane", "Po trzech probach logowania konto zostalo zablokowane.", "W trakcie", 2, 5, 2),
    ("Brak licencji Office", "Komunikat o wygaslej licencji przy starcie Worda.", "W trakcie", 3, 5, 2),
    ("Wolne dzialanie systemu ERP", "System ERP odpowiada z duzym opoznieniem.", "W trakcie", 1, 4, 3),

    ("Skaner nie wykrywa dokumentow", "Skaner nie widzi dokumentu na szybie.", "Rozwiazane", 2, 5, 3),
    ("Problem z Wi-Fi na pietrze 2", "Slaby zasieg sieci bezprzewodowej.", "Rozwiazane", 3, 4, 4),

    ("Reset hasla do systemu kadrowego", "Prosba o reset hasla dla nowego pracownika.", "Zamkniete", 1, 4, 5),
    ("Wymiana klawiatury", "Kilka klawiszy nie dziala, prosze o wymiane.", "Zamkniete", 2, 5, 6),
    ("Konfiguracja poczty na telefonie", "Prosba o pomoc w ustawieniu skrzynki na telefonie.", "Zamkniete", 3, 5, 7),

    # Hurtownia budowlana — powtarzajace sie problemy z siecia w magazynie.
    ("Brak sieci w magazynie", "Terminale w magazynie traca polaczenie z Wi-Fi kilka razy dziennie.", "W trakcie", 7, 4, 1),
    ("Router restartuje sie", "Router w biurze restartuje sie co godzine, caly dzial traci internet.", "Nowe", 7, None, 0),
    ("VPN dla handlowcow nie dziala", "Handlowcy w terenie nie moga polaczyc sie z VPN.", "Rozwiazane", 7, 5, 4),
    ("Drukarka etykiet zacina papier", "Drukarka etykiet w magazynie zacina papier przy kazdym wydruku.", "Zamkniete", 7, 4, 8),

    # Klinika weterynaryjna — sprzet w rejestracji i gabinetach.
    ("Skaner w rejestracji", "Skaner w rejestracji nie wykrywa kart pacjentow.", "Nowe", 8, None, 0),
    ("Program do wizyt sie zawiesza", "Aplikacja do rejestracji wizyt zawiesza sie przy zapisie.", "W trakcie", 8, 5, 1),
    ("Podejrzany zalacznik", "Przyszla faktura z zalacznikiem .exe, wyglada na wirus.", "Nowe", 8, None, 0),
    ("Monitor w gabinecie migocze", "Monitor w gabinecie nr 2 migocze i gasnie.", "Zamkniete", 8, 4, 6),
]


def seed():
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    init_db()

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    klient_id = {
        nazwa: conn.execute("INSERT INTO clients (name) VALUES (?)", (nazwa,)).lastrowid
        for nazwa in CLIENTS
    }

    # Firma kazdego uzytkownika — zgloszenie dziedziczy ja w chwili utworzenia.
    klient_uzytkownika = {}
    for username, password, name, role, email, klient in USERS:
        hashed = generate_password_hash(password)
        uid = conn.execute(
            "INSERT INTO users (username, password, name, role, email, client_id)"
            " VALUES (?,?,?,?,?,?)",
            (username, hashed, name, role, email, klient_id.get(klient)),
        ).lastrowid
        klient_uzytkownika[uid] = klient_id.get(klient)

    # UTC w formacie SQLite — tak samo jak znaczniki zapisywane przez aplikacje.
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    for title, desc, status, created_by, assigned_to, days_ago in TICKETS:
        ai = categorize(title, desc)
        poczatek = now - timedelta(days=days_ago, hours=3)
        created = str(poczatek)
        deadline = str(poczatek + timedelta(hours=SLA_HOURS[ai["priorytet"]]))
        closed = str(now) if status == "Zamkniete" else None

        tid = conn.execute(
            """INSERT INTO tickets
               (title, description, category, priority, status, created_by, assigned_to,
                ai_categorized, ai_pewnosc, sla_deadline, created_at, updated_at, closed_at,
                client_id)
               VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?,?)""",
            (title, desc, ai["kategoria"], ai["priorytet"], status, created_by, assigned_to,
             ai["pewnosc"], deadline, created, created, closed,
             klient_uzytkownika[created_by]),
        ).lastrowid

        conn.execute(
            "INSERT INTO audit_log (ticket_id, user_id, action, new_value, timestamp) VALUES (?,?,?,?,?)",
            (tid, created_by, "Utworzenie", "Nowe", created),
        )
        conn.execute(
            "INSERT INTO audit_log (ticket_id, user_id, action, new_value, timestamp) VALUES (?,?,?,?,?)",
            (tid, None, "Kategoryzacja AI", json.dumps(ai, ensure_ascii=False), created),
        )
        if status in ("W trakcie", "Rozwiazane", "Zamkniete"):
            conn.execute(
                "INSERT INTO audit_log (ticket_id, user_id, action, old_value, new_value, timestamp) VALUES (?,?,?,?,?,?)",
                (tid, assigned_to, "Zmiana statusu", "Nowe", "W trakcie", created),
            )

    conn.commit()

    counts = {
        "klienci": conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
        "uzytkownicy": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "zgloszenia": conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0],
        "otwarte": conn.execute("SELECT COUNT(*) FROM tickets WHERE status != 'Zamkniete'").fetchone()[0],
        "w_trakcie": conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'W trakcie'").fetchone()[0],
        "krytyczne": conn.execute("SELECT COUNT(*) FROM tickets WHERE priority = 'Krytyczny' AND status != 'Zamkniete'").fetchone()[0],
    }
    conn.close()

    print("Baza danych utworzona i wypelniona.")
    print(f"  Klienci:            {counts['klienci']}")
    print(f"  Uzytkownicy:        {counts['uzytkownicy']}")
    print(f"  Zgloszenia (razem): {counts['zgloszenia']}")
    print(f"  Otwarte:            {counts['otwarte']}")
    print(f"  W trakcie:          {counts['w_trakcie']}")
    print(f"  Krytyczne:          {counts['krytyczne']}")


if __name__ == "__main__":
    seed()
