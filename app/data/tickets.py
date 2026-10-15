"""Dostęp do danych zgłoszeń.

Cały SQL dotyczący zgłoszeń jest tutaj — warstwa HTTP nie buduje zapytań.
Dzięki temu widać w jednym miejscu, jakimi zapytaniami system obciąża bazę,
i łatwiej sprawdzić, że każde filtrowanie respektuje granicę dostępu.
"""

from app.data.database import get_db, czas_utc

# Nazwiska i nazwa klienta dołączane przez LEFT JOIN — interfejs pokazuje
# osobę i firmę zamiast surowego identyfikatora.
SELECT_ZGLOSZENIA = """
    SELECT t.*, uc.name created_by_name, ua.name assigned_to_name,
           c.name client_name
    FROM tickets t
    LEFT JOIN users uc ON t.created_by = uc.id
    LEFT JOIN users ua ON t.assigned_to = ua.id
    LEFT JOIN clients c ON t.client_id = c.id
"""


def serialize(t):
    """Wiersz bazy -> słownik odpowiedzi API.

    Pola wyliczane są jawnie: `SELECT *` zwraca też kolumny, których klient
    nie powinien dostać, więc lista poniżej jest świadomą granicą.
    """
    keys = t.keys()
    data = {
        "id":             t["id"],
        "title":          t["title"],
        "description":    t["description"],
        "category":       t["category"],
        "priority":       t["priority"],
        "status":         t["status"],
        "created_by":     t["created_by"],
        "assigned_to":    t["assigned_to"],
        "ai_categorized": bool(t["ai_categorized"]),
        "ai_pewnosc":     t["ai_pewnosc"] if "ai_pewnosc" in keys else None,
        "sla_deadline":   czas_utc(t["sla_deadline"]),
        "created_at":     czas_utc(t["created_at"]),
        "updated_at":     czas_utc(t["updated_at"]),
        "closed_at":      czas_utc(t["closed_at"]),
        "client_id":      t["client_id"],
    }
    if "created_by_name" in keys:
        data["created_by_name"] = t["created_by_name"]
    if "assigned_to_name" in keys:
        data["assigned_to_name"] = t["assigned_to_name"]
    if "client_name" in keys:
        data["client_name"] = t["client_name"]
    return data


def zbuduj_warunki(user, filtry):
    """Warunki WHERE zależne od roli.

    Dla pracownika ograniczenie do własnych zgłoszeń jest **pierwszym**
    warunkiem i nie da się go pominąć parametrami filtrowania — to twarda
    granica dostępu, nie ukrywanie danych w interfejsie.
    """
    warunki, params = [], []

    if user["role"] == "pracownik":
        warunki.append("t.created_by = ?")
        params.append(user["id"])
    else:
        for pole in ("status", "priority", "category", "client_id"):
            wartosc = filtry.get(pole)
            if wartosc:
                warunki.append(f"t.{pole} = ?")
                params.append(wartosc)

    where = (" WHERE " + " AND ".join(warunki)) if warunki else ""
    return where, params


def policz(where, params):
    return get_db().execute(
        f"SELECT COUNT(*) c FROM tickets t{where}", params
    ).fetchone()["c"]


def strona(where, params, limit, offset):
    return get_db().execute(
        SELECT_ZGLOSZENIA + where + " ORDER BY t.id DESC LIMIT ? OFFSET ?",
        list(params) + [limit, offset],
    ).fetchall()


def pobierz(ticket_id):
    return get_db().execute(
        SELECT_ZGLOSZENIA + " WHERE t.id = ?", (ticket_id,)
    ).fetchone()


def pobierz_surowe(ticket_id):
    """Bez złączeń — gdy potrzebny jest tylko stan zgłoszenia."""
    return get_db().execute(
        "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
    ).fetchone()


def istnieje(ticket_id):
    return get_db().execute(
        "SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)
    ).fetchone() is not None


def utworz(title, description, created_by, client_id,
           kategoria, priorytet, pewnosc, sla_deadline):
    """Zgłoszenie od razu z wynikiem kategoryzacji — jednym zapisem.

    Kategoryzacja nie potrzebuje identyfikatora zgłoszenia, więc nie ma
    powodu zapisywać wiersza, a potem go poprawiać drugim UPDATE.
    """
    return get_db().execute(
        "INSERT INTO tickets (title, description, created_by, client_id, category,"
        " priority, ai_categorized, ai_pewnosc, sla_deadline)"
        " VALUES (?,?,?,?,?,?,1,?,?)",
        (title, description, created_by, client_id, kategoria, priorytet,
         pewnosc, sla_deadline),
    ).lastrowid


def zmien_status(ticket_id, obecny_status, nowy_status, przypisz_do=None, zamknij=False):
    """Zmiana statusu pod warunkiem, że nikt go w międzyczasie nie zmienił.

    Zwraca False, gdy status w bazie jest już inny niż `obecny_status` —
    np. dwóch techników jednocześnie podejmuje to samo zgłoszenie. Bez tego
    warunku obaj przeszliby walidację na nieaktualnym odczycie, a drugi
    zapis nadpisałby przypisanie pierwszego.

    Przypisanie przy podjęciu też jest warunkowe (COALESCE) — nie zastępuje
    opiekuna ustawionego w międzyczasie.
    """
    sql = "UPDATE tickets SET status = ?, updated_at = datetime('now')"
    params = [nowy_status]
    if przypisz_do is not None:
        sql += ", assigned_to = COALESCE(assigned_to, ?)"
        params.append(przypisz_do)
    if zamknij:
        sql += ", closed_at = datetime('now')"
    sql += " WHERE id = ? AND status = ?"
    params += [ticket_id, obecny_status]
    return get_db().execute(sql, params).rowcount == 1


def zmien_kategorie(ticket_id, kategoria):
    get_db().execute(
        "UPDATE tickets SET category = ?, updated_at = datetime('now') WHERE id = ?",
        (kategoria, ticket_id),
    )


def zmien_przypisanie(ticket_id, uzytkownik_id, tylko_wolne_dla=None):
    """Zmiana opiekuna zgłoszenia; None zwalnia przypisanie.

    `tylko_wolne_dla` — technik, który bierze zgłoszenie sam: zapis udaje się
    tylko wtedy, gdy zgłoszenie jest wolne albo już jest jego. Warunek leży
    w tym samym UPDATE, więc dwóch techników klikających „Przypisz do mnie"
    jednocześnie nie nadpisze się nawzajem. Zwraca False, gdy ktoś był szybszy.
    """
    sql = "UPDATE tickets SET assigned_to = ?, updated_at = datetime('now') WHERE id = ?"
    params = [uzytkownik_id, ticket_id]
    if tylko_wolne_dla is not None:
        sql += " AND (assigned_to IS NULL OR assigned_to = ?)"
        params.append(tylko_wolne_dla)
    return get_db().execute(sql, params).rowcount == 1


# --- Kolejka kierownika ------------------------------------------------

# Statusy otwarte wymienione wprost, a nie jako „NOT IN (zamknięte)" — tylko
# wtedy SQLite może sięgnąć po indeks statusu zamiast przeglądać wszystkie
# zgłoszenia. Zgodność z maszyną stanów sprawdza test.
STATUSY_OTWARTE = ("Nowe", "W trakcie", "Wstrzymane")
_OTWARTE = "t.status IN ('Nowe', 'W trakcie', 'Wstrzymane')"
# Najpilniejsze najpierw; zgłoszenia bez terminu na końcu.
_WG_TERMINU = " ORDER BY t.sla_deadline IS NULL, julianday(t.sla_deadline), t.id"


def nieprzypisane(limit):
    """Otwarte zgłoszenia bez opiekuna — (liczba wszystkich, najpilniejsze)."""
    db = get_db()
    liczba = db.execute(
        f"SELECT COUNT(*) FROM tickets t WHERE {_OTWARTE} AND t.assigned_to IS NULL"
    ).fetchone()[0]
    wiersze = db.execute(
        SELECT_ZGLOSZENIA + f" WHERE {_OTWARTE} AND t.assigned_to IS NULL"
        + _WG_TERMINU + " LIMIT ?", (limit,)
    ).fetchall()
    return liczba, wiersze


def zagrozone(granica, limit):
    """Otwarte zgłoszenia z terminem SLA przed `granica` (także już minionym)."""
    db = get_db()
    warunek = (f" WHERE {_OTWARTE} AND t.sla_deadline IS NOT NULL"
               " AND julianday(t.sla_deadline) < julianday(?)")
    liczba = db.execute("SELECT COUNT(*) FROM tickets t" + warunek, (granica,)).fetchone()[0]
    wiersze = db.execute(
        SELECT_ZGLOSZENIA + warunek + _WG_TERMINU + " LIMIT ?", (granica, limit)
    ).fetchall()
    return liczba, wiersze


def otwarte_przypisane(uzytkownik_id, limit):
    """Otwarte zgłoszenia technika, od najpilniejszego."""
    return get_db().execute(
        SELECT_ZGLOSZENIA + f" WHERE {_OTWARTE} AND t.assigned_to = ?"
        + _WG_TERMINU + " LIMIT ?", (uzytkownik_id, limit)
    ).fetchall()


# --- Notatki -----------------------------------------------------------

def notatki(ticket_id, tylko_jawne):
    """Notatki zgłoszenia; pracownik nie widzi wewnętrznych."""
    sql = ("SELECT n.*, u.name author FROM notes n "
           "JOIN users u ON n.author_id = u.id WHERE n.ticket_id = ?")
    if tylko_jawne:
        sql += " AND n.internal = 0"
    rows = get_db().execute(sql + " ORDER BY n.id", (ticket_id,)).fetchall()
    return [
        {"author": n["author"], "content": n["content"],
         "internal": bool(n["internal"]), "created_at": czas_utc(n["created_at"])}
        for n in rows
    ]


def dodaj_notatke(ticket_id, author_id, content, internal):
    get_db().execute(
        "INSERT INTO notes (ticket_id, author_id, content, internal) VALUES (?,?,?,?)",
        (ticket_id, author_id, content, 1 if internal else 0),
    )


# --- Statystyki --------------------------------------------------------

def _warunek_autora(autor_id):
    """Ograniczenie statystyk do zgłoszeń jednego autora (pulpit pracownika)."""
    if autor_id is None:
        return "", ()
    return " WHERE created_by = ?", (autor_id,)


def statystyki(autor_id=None):
    """Liczniki pulpitu jednym przejściem po tabeli zamiast pięcioma."""
    where, params = _warunek_autora(autor_id)
    wiersz = get_db().execute(f"""
        SELECT
            COUNT(*)                                                AS wszystkie,
            SUM(status != 'Zamkniete')                              AS otwarte,
            SUM(status =  'W trakcie')                              AS w_trakcie,
            SUM(status =  'Rozwiazane')                             AS rozwiazane,
            SUM(status =  'Zamkniete')                              AS zamkniete,
            SUM(priority = 'Krytyczny' AND status != 'Zamkniete')   AS krytyczne
        FROM tickets{where}
    """, params).fetchone()

    # SUM() zwraca NULL dla pustego zbioru — pulpit ma pokazac zera.
    klucze = ("wszystkie", "otwarte", "w_trakcie", "rozwiazane", "zamkniete", "krytyczne")
    return {k: wiersz[k] or 0 for k in klucze}


def rozklad_kategorii(autor_id=None):
    where, params = _warunek_autora(autor_id)
    rows = get_db().execute(
        f"SELECT category, COUNT(*) c FROM tickets{where}"
        + (" AND" if where else " WHERE") + " category IS NOT NULL"
        " GROUP BY category ORDER BY c DESC",
        params,
    ).fetchall()
    return [{"kategoria": r["category"], "liczba": r["c"]} for r in rows]
