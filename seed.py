import sqlite3
import os
import json
import random
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

# Historia z ostatnich miesiecy — zeby raporty mialy trend, porownanie
# z poprzednim okresem i dane o dotrzymaniu SLA. Kazda firma ma wlasny profil
# awarii i wlasne tempo obslugi.
#
#   autor: (szablony zgloszen, liczba zgloszen, czas rozwiazania jako
#           ulamek terminu SLA — od, do; powyzej 1.0 oznacza przekroczenie)
HISTORIA = {
    1: ([("Kasa nie laczy sie z internetem", "Terminal platniczy w sklepie traci polaczenie z siecia."),
         ("Drukarka paragonow nie drukuje", "Drukarka przy kasie zacina papier."),
         ("Nie dochodza zamowienia mailem", "Zamowienia od klientow nie trafiaja do skrzynki pocztowej."),
         ("Laptop w biurze sie przegrzewa", "Laptop kierownika przegrzewa sie po godzinie pracy.")],
        22, (0.3, 1.1)),
    2: ([("Program ksiegowy sie zawiesza", "System ksiegowy zawiesza sie przy zamykaniu miesiaca."),
         ("Wygasla licencja programu", "Program pokazuje komunikat o wygaslej licencji."),
         ("Reset hasla do systemu", "Pracownik zapomnial hasla do logowania."),
         ("Excel nie otwiera raportow", "Excel zawiesza sie przy otwieraniu duzych plikow.")],
        26, (0.2, 0.8)),
    3: ([("Podejrzany mail od klienta", "Wiadomosc z prosba o podanie hasla, wyglada na phishing."),
         ("Outlook nie wysyla poczty", "Wiadomosci zostaja w skrzynce nadawczej Outlook."),
         ("Brak dostepu do folderu", "Nie mam uprawnien do folderu z aktami spraw."),
         ("Zablokowane konto", "Konto zostalo zablokowane po kilku probach logowania.")],
        20, (0.4, 1.3)),
    7: ([("Brak Wi-Fi w magazynie", "Terminale w magazynie traca polaczenie z siecia wifi."),
         ("VPN nie dziala w terenie", "Handlowcy nie moga polaczyc sie z VPN."),
         ("Router w hali sie restartuje", "Router restartuje sie kilka razy dziennie."),
         ("Drukarka etykiet zacina papier", "Drukarka etykiet w magazynie zacina papier.")],
        30, (0.6, 2.2)),
    8: ([("Monitor w gabinecie gasnie", "Monitor w gabinecie migocze i gasnie."),
         ("Aplikacja do wizyt sie zawiesza", "Program do rejestracji wizyt zawiesza sie przy zapisie."),
         ("Skaner nie wykrywa kart", "Skaner w rejestracji nie wykrywa kart pacjentow."),
         ("Komputer nie startuje", "Stacja robocza w rejestracji nie uruchamia sie rano.")],
        18, (0.3, 1.0)),
}
HISTORIA_DNI = (9, 120)       # historia konczy sie tam, gdzie zaczynaja TICKETS
TECHNICY = (4, 5)


def _dodaj_zgloszenie(conn, title, desc, status, created_by, assigned_to, client_id,
                      utworzono, rozwiazano=None, zamknieto=None):
    """Zgloszenie wraz z historia zmian spojna z jego statusem."""
    ai = categorize(title, desc)
    created = str(utworzono)
    tid = conn.execute(
        """INSERT INTO tickets
           (title, description, category, priority, status, created_by, assigned_to,
            ai_categorized, ai_pewnosc, sla_deadline, created_at, updated_at, closed_at,
            client_id)
           VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?,?)""",
        (title, desc, ai["kategoria"], ai["priorytet"], status, created_by, assigned_to,
         ai["pewnosc"], str(utworzono + timedelta(hours=SLA_HOURS[ai["priorytet"]])),
         created, str(zamknieto or rozwiazano or utworzono),
         str(zamknieto) if zamknieto else None, client_id),
    ).lastrowid

    wpisy = [(created_by, "Utworzenie", None, "Nowe", created),
             (None, "Kategoryzacja AI", None, json.dumps(ai, ensure_ascii=False), created)]
    if status != "Nowe":
        wpisy.append((assigned_to, "Zmiana statusu", "Nowe", "W trakcie",
                      str(utworzono + timedelta(minutes=15))))
    if rozwiazano:
        wpisy.append((assigned_to, "Zmiana statusu", "W trakcie", "Rozwiazane", str(rozwiazano)))
    if zamknieto:
        wpisy.append((assigned_to, "Zmiana statusu", "Rozwiazane", "Zamkniete", str(zamknieto)))
    conn.executemany(
        "INSERT INTO audit_log (ticket_id, user_id, action, old_value, new_value, timestamp)"
        " VALUES (?,?,?,?,?,?)", [(tid, *w) for w in wpisy])
    return ai


def _rozwiazanie(utworzono, priorytet, ulamek, now):
    """Chwila rozwiazania jako ulamek terminu SLA — nie pozniej niz godzine temu."""
    return min(utworzono + timedelta(hours=SLA_HOURS[priorytet] * ulamek),
               now - timedelta(hours=1))


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

    # Historia — starsza od zgloszen z listy TICKETS i zawsze identyczna
    # (staly zarodek losowania), wiec raporty z danych demonstracyjnych sa
    # powtarzalne. Identyfikatory rosna wraz z data, jak w prawdziwej bazie.
    los = random.Random(2026)
    historia = []
    for autor, (szablony, liczba, (szybko, wolno)) in HISTORIA.items():
        for _ in range(liczba):
            title, desc = los.choice(szablony)
            utworzono = now - timedelta(days=los.randint(*HISTORIA_DNI),
                                        hours=los.randint(0, 9), minutes=los.randint(0, 59))
            historia.append((utworzono, title, desc, autor, los.choice(TECHNICY),
                             los.uniform(szybko, wolno), los.uniform(1, 30)))
    for utworzono, title, desc, autor, technik, ulamek, do_zamkniecia in sorted(historia):
        priorytet = categorize(title, desc)["priorytet"]
        rozwiazano = _rozwiazanie(utworzono, priorytet, ulamek, now)
        _dodaj_zgloszenie(conn, title, desc, "Zamkniete", autor, technik,
                          klient_uzytkownika[autor], utworzono, rozwiazano,
                          rozwiazano + timedelta(hours=do_zamkniecia))

    for title, desc, status, created_by, assigned_to, days_ago in sorted(
            TICKETS, key=lambda t: -t[5]):
        utworzono = now - timedelta(days=days_ago, hours=3)
        rozwiazano = zamknieto = None
        if status in ("Rozwiazane", "Zamkniete"):
            priorytet = categorize(title, desc)["priorytet"]
            rozwiazano = _rozwiazanie(utworzono, priorytet, 0.7, now)
        if status == "Zamkniete":
            zamknieto = min(rozwiazano + timedelta(hours=4), now)
        _dodaj_zgloszenie(conn, title, desc, status, created_by, assigned_to,
                          klient_uzytkownika[created_by], utworzono, rozwiazano, zamknieto)

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
